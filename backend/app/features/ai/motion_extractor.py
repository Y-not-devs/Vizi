"""Модуль предобработки видео и детекции аномалий с использованием Rolling Median Temporal Window.

Разработан для сервиса ForteWatch (FastAPI + OpenCV + Ollama VLM).
Решает проблему потери мелких деталей (чеки, купюры, смартфоны) при наивном сжатии кадра,
выделяя Dynamic ROI в исходном разрешении и отсекая статические кадры без движения.
"""

from __future__ import annotations

import base64
import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, NamedTuple

import cv2
import numpy as np

logger = logging.getLogger("fortewatch.motion_extractor")

# Константы по умолчанию по ТЗ
DEFAULT_SAMPLE_FPS: Final[float] = 1.0  # 1 кадр в секунду
DEFAULT_BUFFER_SIZE: Final[int] = 5  # Окно 5 секунд
DEFAULT_PROCESSING_WIDTH: Final[int] = 640
DEFAULT_PROCESSING_HEIGHT: Final[int] = 360
DEFAULT_MIN_CONTOUR_AREA: Final[float] = 500.0  # px на разрешении 640x360
DEFAULT_PADDING_PX: Final[int] = 45  # Отступ 40-50 px со всех сторон
DEFAULT_DIFF_THRESHOLD: Final[int] = 25  # Порог бинаризации cv2.threshold
DEFAULT_MAX_ACTIVE_SEGMENTS: Final[int] = 15  # Топ-N активных кадров для инференса VLM < 100s
DEFAULT_JPEG_QUALITY: Final[int] = 85


class BoundingBox(NamedTuple):
    """Координаты ограничивающего прямоугольника [x_min, y_min, x_max, y_max]."""

    x_min: int
    y_min: int
    x_max: int
    y_max: int

    @property
    def width(self) -> int:
        return max(0, self.x_max - self.x_min)

    @property
    def height(self) -> int:
        return max(0, self.y_max - self.y_min)

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass(slots=True, frozen=True)
class MotionDetectionResult:
    """Результат детекции движения для отдельного кадра."""

    has_motion: bool
    motion_score: float
    roi_bbox: BoundingBox | None
    active_contours_count: int


@dataclass(slots=True, frozen=True)
class ActiveFrameSegment:
    """Сегмент активного движения с закодированными кадрами для передачи в VLM."""

    timecode_sec: float
    crop_base64: str
    full_frame_base64: str
    motion_score: float

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в формат, требуемый ТЗ."""
        return {
            "timecode_sec": self.timecode_sec,
            "crop_base64": self.crop_base64,
            "full_frame_base64": self.full_frame_base64,
            "motion_score": self.motion_score,
        }


class TemporalMotionAnalyzer:
    """Анализатор движения на основе скользящего временного медианного окна.

    Особенности реализации:
    1. Скользящее окно (deque) из последних N кадров (1 FPS): динамический фон вычисляется
       как попиксельная медиана (np.median) по серому каналу. Это исключает зависимость
       от статичного первого кадра и нивелирует влияние ракурса камеры и постепенных
       изменений освещения.
    2. Двухуровневая обработка разрешения: детекция движения выполняется на легком разрешении
       (640x360) для максимальной скорости (CPU-friendly, <5 мс на кадр), а Dynamic ROI
       вырезается из ОРИГИНАЛЬНОГО цветного кадра (Full HD / 720p) с сохранением чеков,
       купюр и экранов телефонов.
    3. Отсечение статики: кадры без значимых контуров отбрасываются, экономя лимит инференса VLM.
    4. Ограничение топ-N кадров по motion_score гарантирует завершение анализа за <100 сек.
    """

    def __init__(
        self,
        sample_fps: float = DEFAULT_SAMPLE_FPS,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        processing_resolution: tuple[int, int] = (
            DEFAULT_PROCESSING_WIDTH,
            DEFAULT_PROCESSING_HEIGHT,
        ),
        min_contour_area: float = DEFAULT_MIN_CONTOUR_AREA,
        padding_px: int = DEFAULT_PADDING_PX,
        threshold_val: int = DEFAULT_DIFF_THRESHOLD,
        max_active_segments: int = DEFAULT_MAX_ACTIVE_SEGMENTS,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
    ) -> None:
        if sample_fps <= 0:
            raise ValueError(f"sample_fps must be positive, got {sample_fps}")
        if buffer_size < 2:
            raise ValueError(f"buffer_size must be at least 2 for median, got {buffer_size}")
        if min_contour_area <= 0:
            raise ValueError(f"min_contour_area must be positive, got {min_contour_area}")

        self.sample_fps = sample_fps
        self.buffer_size = buffer_size
        self.proc_w, self.proc_h = processing_resolution
        self.min_contour_area = min_contour_area
        self.padding_px = padding_px
        self.threshold_val = threshold_val
        self.max_active_segments = max_active_segments
        self.jpeg_quality = jpeg_quality

        # Структурный элемент для морфологического закрытия (склеивание шумов)
        self._morph_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        self._dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    def _preprocess_for_motion(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Даунскейл и конвертация в градации серого с подавлением высокочастотного шума."""
        resized = cv2.resize(
            frame_bgr,
            (self.proc_w, self.proc_h),
            interpolation=cv2.INTER_AREA,
        )
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        # Легкий гауссов фильтр для сглаживания матричного шума камеры
        return cv2.GaussianBlur(gray, (5, 5), 0)

    def _compute_median_background(self, buffer: deque[np.ndarray]) -> np.ndarray:
        """Попиксельная медиана по буферу кадров.

        Гарантирует отсутствие утечек памяти: временный стек создается как локальный
        C-contiguous массив и сразу преобразуется в uint8.
        """
        # np.stack формирует временный массив формы (N, H, W)
        stack = np.stack(list(buffer), axis=0)
        median = np.median(stack, axis=0).astype(np.uint8)
        del stack
        return median

    def _detect_motion(
        self,
        current_gray: np.ndarray,
        median_bg: np.ndarray,
    ) -> MotionDetectionResult:
        """Вычисление разницы с фоном, фильтрация шумов и поиск внешних контуров."""
        # 1. Попиксельная абсолютная разность
        diff = cv2.absdiff(current_gray, median_bg)

        # 2. Пороговая бинаризация
        _, thresh = cv2.threshold(diff, self.threshold_val, 255, cv2.THRESH_BINARY)

        # 3. Морфологическое закрытие (MORPH_CLOSE) для объединения разрозненных пятен
        # и последующая легкая дилатация
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, self._morph_kernel, iterations=2)
        dilated = cv2.dilate(closed, self._dilate_kernel, iterations=1)

        # 4. Поиск внешних контуров
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 5. Фильтрация контуров по минимальной площади (min_contour_area)
        valid_contours: list[np.ndarray] = []
        total_motion_area = 0.0

        for c in contours:
            area = float(cv2.contourArea(c))
            if area >= self.min_contour_area:
                valid_contours.append(c)
                total_motion_area += area

        if not valid_contours:
            return MotionDetectionResult(
                has_motion=False,
                motion_score=0.0,
                roi_bbox=None,
                active_contours_count=0,
            )

        # 6. Объединение всех валидных контуров в единый Bounding Box
        x_min = self.proc_w
        y_min = self.proc_h
        x_max = 0
        y_max = 0

        for c in valid_contours:
            x, y, w, h = cv2.boundingRect(c)
            x_min = min(x_min, x)
            y_min = min(y_min, y)
            x_max = max(x_max, x + w)
            y_max = max(y_max, y + h)

        bbox = BoundingBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)

        return MotionDetectionResult(
            has_motion=True,
            motion_score=total_motion_area,
            roi_bbox=bbox,
            active_contours_count=len(valid_contours),
        )

    def _extract_roi_crop(
        self,
        orig_frame: np.ndarray,
        roi_bbox: BoundingBox,
    ) -> np.ndarray:
        """Перенос Bounding Box на оригинальное разрешение кадра с добавлением паддинга."""
        orig_h, orig_w = orig_frame.shape[:2]

        scale_x = orig_w / float(self.proc_w)
        scale_y = orig_h / float(self.proc_h)

        # Масштабируем координаты на оригинальный кадр
        mapped_x_min = int(roi_bbox.x_min * scale_x)
        mapped_y_min = int(roi_bbox.y_min * scale_y)
        mapped_x_max = int(roi_bbox.x_max * scale_x)
        mapped_y_max = int(roi_bbox.y_max * scale_y)

        # Добавляем padding (40-50 px) с безопасным ограничением границ
        final_x_min = max(0, mapped_x_min - self.padding_px)
        final_y_min = max(0, mapped_y_min - self.padding_px)
        final_x_max = min(orig_w, mapped_x_max + self.padding_px)
        final_y_max = min(orig_h, mapped_y_max + self.padding_px)

        # Проверка вырожденных размеров
        if final_x_max <= final_x_min or final_y_max <= final_y_min:
            return orig_frame

        crop = orig_frame[final_y_min:final_y_max, final_x_min:final_x_max]
        return crop

    def _encode_jpeg_base64(self, image: np.ndarray, quality: int | None = None) -> str:
        """Кодирование изображения в JPEG base64 с защитой памяти."""
        q = quality or self.jpeg_quality
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), q]
        success, buffer = cv2.imencode(".jpg", image, encode_params)
        if not success or buffer is None:
            raise RuntimeError("Failed to encode image to JPEG format")
        return base64.b64encode(buffer).decode("utf-8")

    def extract_active_segments(self, video_path: str | Path) -> list[dict[str, Any]]:
        """Извлечение значимых таймкодов с динамическим ROI для передачи в VLM.

        Args:
            video_path: Путь к исходному видеофайлу.

        Returns:
            Список словарей:
            [
                {
                    "timecode_sec": float,
                    "crop_base64": str,
                    "full_frame_base64": str,
                    "motion_score": float,
                }
            ]

        Raises:
            FileNotFoundError: Если файл не найден.
            ValueError: Если видеофайл поврежден или не содержит кадров.
        """
        path = Path(video_path)
        if not path.is_file():
            raise FileNotFoundError(f"Video file not found: {path}")

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise ValueError(f"Failed to open video file via cv2.VideoCapture: {path}")

        try:
            return self._process_video_stream(cap)
        finally:
            cap.release()

    def _process_video_stream(self, cap: cv2.VideoCapture) -> list[dict[str, Any]]:
        """Основной цикл обработки видеопотока с контролем ресурсов."""
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if fps <= 0 or np.isnan(fps):
            fps = 25.0
            logger.warning("Unreliable FPS from metadata, defaulting to %.1f FPS", fps)

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps if total_frames > 0 else 0.0
        logger.info(
            "Starting motion analysis: fps=%.2f, total_frames=%d, estimated_duration=%.1fs",
            fps,
            total_frames,
            duration_sec,
        )

        # Вычисляем шаг между выборками для частоты 1 FPS
        step = max(1, int(round(fps / self.sample_fps)))

        # Скользящий кольцевой буфер для кадров (хранит только легковесные серые маски)
        gray_buffer: deque[np.ndarray] = deque(maxlen=self.buffer_size)

        candidate_segments: list[ActiveFrameSegment] = []
        frame_idx = 0

        while True:
            # Считываем только нужные кадры с шагом step
            ret, frame_bgr = cap.read()
            if not ret or frame_bgr is None:
                break

            if frame_idx % step != 0:
                frame_idx += 1
                continue

            current_timecode = round(frame_idx / fps, 3)

            # 1. Легковесный препроцессинг (640x360 Gray + Blur)
            gray_proc = self._preprocess_for_motion(frame_bgr)
            gray_buffer.append(gray_proc)

            # Для вычисления медианы необходимо накопить хотя бы 2 кадра
            if len(gray_buffer) >= 2:
                # 2. Вычисление динамического фона скользящего окна
                median_bg = self._compute_median_background(gray_buffer)

                # 3. Детекция движения
                motion_res = self._detect_motion(gray_proc, median_bg)

                # 4. Если движение есть — формируем ROI и кодируем в base64
                if motion_res.has_motion and motion_res.roi_bbox is not None:
                    # Вырезаем область высокого разрешения из ОРИГИНАЛЬНОГО цветного кадра
                    crop = self._extract_roi_crop(frame_bgr, motion_res.roi_bbox)

                    crop_b64 = self._encode_jpeg_base64(crop, quality=self.jpeg_quality)
                    # Сжатый полный кадр (75% качество) для контекста сцены
                    full_b64 = self._encode_jpeg_base64(frame_bgr, quality=75)

                    segment = ActiveFrameSegment(
                        timecode_sec=current_timecode,
                        crop_base64=crop_b64,
                        full_frame_base64=full_b64,
                        motion_score=motion_res.motion_score,
                    )
                    candidate_segments.append(segment)

            frame_idx += 1

        logger.info(
            "Video processed: %d candidate active frames found out of sampled frames",
            len(candidate_segments),
        )

        # 5. Ограничение топ-N наиболее активных моментов по motion_score
        # для гарантии лимита инференса VLM < 100 секунд
        if len(candidate_segments) > self.max_active_segments:
            # Сортируем по убыванию motion_score и берем топ-N
            top_segments = sorted(
                candidate_segments,
                key=lambda s: s.motion_score,
                reverse=True,
            )[: self.max_active_segments]

            # Восстанавливаем хронологический порядок для логичной причинно-следственной цепочки VLM
            top_segments.sort(key=lambda s: s.timecode_sec)
            selected = top_segments
        else:
            selected = candidate_segments

        logger.info(
            "Selected %d high-activity segments for VLM inference",
            len(selected),
        )

        return [seg.to_dict() for seg in selected]
