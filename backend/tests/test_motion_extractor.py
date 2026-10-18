"""Тесты для TemporalMotionAnalyzer (ForteWatch Rolling Median Temporal Window)."""

import base64
import tempfile
from collections.abc import Generator
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.features.ai.motion_extractor import (
    BoundingBox,
    TemporalMotionAnalyzer,
)


@pytest.fixture
def sample_video_path() -> Generator[Path, None, None]:
    """Генерация тестового синтетического видео (10 секунд, 10 FPS, 1280x720):

    - 0-3 сек: статичный кадр (прилавок)
    - 4-7 сек: движение яркого объекта (имитация руки/телефона в лотке)
    - 8-10 сек: статичный кадр
    """
    fps = 10.0
    width = 1280
    height = 720
    duration_sec = 10
    total_frames = int(fps * duration_sec)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(tmp_path), fourcc, fps, (width, height))

    try:
        # Базовый статичный фон: градиент стола кассы
        base_bg = np.zeros((height, width, 3), dtype=np.uint8)
        base_bg[:, :] = [180, 160, 140]  # Светло-серый тон
        cv2.putText(
            base_bg,
            "CASH DESK 01",
            (50, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.5,
            (50, 50, 50),
            2,
        )

        for i in range(total_frames):
            frame = base_bg.copy()
            sec = i / fps

            # В интервале 4.0 - 7.0 секунд симулируем активное движение (перемещение прямоугольника)
            if 4.0 <= sec <= 7.0:
                pos_x = int(300 + (sec - 4.0) * 150)
                pos_y = int(250 + (sec - 4.0) * 50)
                # Рисуем "телефон/руку" (140x220 px)
                cv2.rectangle(
                    frame,
                    (pos_x, pos_y),
                    (pos_x + 140, pos_y + 220),
                    (20, 20, 220),
                    -1,
                )

            out.write(frame)
    finally:
        out.release()

    yield tmp_path

    if tmp_path.exists():
        tmp_path.unlink()


def test_analyzer_init_validation() -> None:
    """Проверка валидации входных параметров анализатора."""
    with pytest.raises(ValueError, match="sample_fps must be positive"):
        TemporalMotionAnalyzer(sample_fps=0.0)

    with pytest.raises(ValueError, match="buffer_size must be at least 2"):
        TemporalMotionAnalyzer(buffer_size=1)

    with pytest.raises(ValueError, match="min_contour_area must be positive"):
        TemporalMotionAnalyzer(min_contour_area=-10.0)


def test_bounding_box_properties() -> None:
    """Проверка вычисления размеров и площади BoundingBox."""
    bbox = BoundingBox(x_min=10, y_min=20, x_max=110, y_max=120)
    assert bbox.width == 100
    assert bbox.height == 100
    assert bbox.area == 10000


def test_static_frames_suppression() -> None:
    """Проверка, что на серии одинаковых кадров has_motion=False."""
    analyzer = TemporalMotionAnalyzer(min_contour_area=300.0)
    static_frame = np.full((720, 1280, 3), 120, dtype=np.uint8)

    # Заполняем буфер одинаковыми кадрами
    from collections import deque

    buf: deque[np.ndarray] = deque(maxlen=5)
    gray = analyzer._preprocess_for_motion(static_frame)
    for _ in range(5):
        buf.append(gray)

    median_bg = analyzer._compute_median_background(buf)
    res = analyzer._detect_motion(gray, median_bg)

    assert not res.has_motion
    assert res.motion_score == 0.0
    assert res.roi_bbox is None


def test_motion_detection_and_roi_crop() -> None:
    """Проверка корректности детекции движения, вычисления ROI и кодирования в base64."""
    analyzer = TemporalMotionAnalyzer(
        min_contour_area=100.0,
        padding_px=45,
    )

    h, w = 720, 1280
    bg = np.full((h, w, 3), 100, dtype=np.uint8)

    from collections import deque

    buf: deque[np.ndarray] = deque(maxlen=5)
    for _ in range(5):
        buf.append(analyzer._preprocess_for_motion(bg))

    # Создаем кадр с контрастным объектом по центру
    active_frame = bg.copy()
    cv2.rectangle(active_frame, (500, 300), (700, 500), (255, 255, 255), -1)

    curr_gray = analyzer._preprocess_for_motion(active_frame)
    median_bg = analyzer._compute_median_background(buf)
    res = analyzer._detect_motion(curr_gray, median_bg)

    assert res.has_motion
    assert res.motion_score > 0
    assert res.roi_bbox is not None

    # Проверяем вырезку кропа из оригинального кадра с паддингом
    crop = analyzer._extract_roi_crop(active_frame, res.roi_bbox)
    assert crop.ndim == 3
    assert crop.shape[0] > 0
    assert crop.shape[1] > 0
    # Проверяем, что кроп не превышает размеры исходного кадра
    assert crop.shape[0] <= h
    assert crop.shape[1] <= w

    # Проверяем base64 кодирование
    b64 = analyzer._encode_jpeg_base64(crop)
    assert isinstance(b64, str)
    decoded = base64.b64decode(b64)
    # Проверка магических байтов JPEG (0xFF, 0xD8)
    assert decoded[:2] == b"\xff\xd8"


def test_extract_active_segments_end_to_end(sample_video_path: Path) -> None:
    """Сквозной тест extract_active_segments на видеофайле."""
    analyzer = TemporalMotionAnalyzer(
        sample_fps=1.0,
        buffer_size=5,
        min_contour_area=300.0,
        max_active_segments=15,
    )

    segments = analyzer.extract_active_segments(sample_video_path)

    # Проверяем формат возвращаемого словаря по ТЗ
    assert isinstance(segments, list)
    assert len(segments) > 0
    assert len(segments) <= 15

    for seg in segments:
        assert "timecode_sec" in seg
        assert "crop_base64" in seg
        assert "full_frame_base64" in seg
        assert "motion_score" in seg

        assert isinstance(seg["timecode_sec"], float)
        assert isinstance(seg["crop_base64"], str)
        assert isinstance(seg["full_frame_base64"], str)
        assert isinstance(seg["motion_score"], float)

        # Активное движение было с 4.0 по 7.0 секунду: таймкоды должны попадать в этот период
        assert 3.5 <= seg["timecode_sec"] <= 8.0

    # Проверяем хронологическую сортировку таймкодов
    timecodes = [s["timecode_sec"] for s in segments]
    assert timecodes == sorted(timecodes)


def test_file_not_found_handling() -> None:
    """Проверка корректной ошибки при отсутствии видеофайла."""
    analyzer = TemporalMotionAnalyzer()
    with pytest.raises(FileNotFoundError):
        analyzer.extract_active_segments("/non/existent/path/video.mp4")
