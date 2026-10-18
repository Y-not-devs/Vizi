"""Нормативный видеоаннотатор Vizi (HUD, Dynamic Zones, FSM, H.264 Web Player).

Отрисовывает поверх кадров:
1. Статические полигоны зон кассового узла (Зона кассира, Зона клиента, Зона дверей).
2. Динамическую зону активности лотка пересчета (Exchange Tray / Dynamic ROI).
3. Bounding Boxes объектов с динамическим повышением роли (CASHIER, VERIFIED, UNAUTHORIZED).
4. Нормативный HUD-баннер мониторинга безопасности (таймкод, FPS, статья Правил № 231, вердикт).
5. Автоматическое кодирование в веб-совместимый H.264 MP4 для мгновенного стриминга в браузере.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections import deque
from pathlib import Path
from typing import Final, NamedTuple

import cv2
import numpy as np
from ultralytics import YOLO

from app.features.ai.compliance_fsm import (
    COLOR_CLIENT_VERIFIED,
    COLOR_VIOLATION,
    BankComplianceFSM,
    BankDeskZones,
    FrameDetections,
    NormalizedZone,
    SessionType,
    VLMComplianceJudge,
    filter_reflection_and_assign_roles,
    get_person_display_attributes,
    is_customer_at_desk,
    is_real_phone_violation,
    should_trigger_id_verification,
)
from app.features.ai.motion_extractor import BoundingBox, TemporalMotionAnalyzer

logger = logging.getLogger(__name__)

# Цветовая палитра BGR
COLOR_PERSON: Final[tuple[int, int, int]] = (60, 220, 80)       # Зеленый
COLOR_PHONE: Final[tuple[int, int, int]] = (40, 40, 240)        # Красный (Алерт)
COLOR_ROI_CASH: Final[tuple[int, int, int]] = (255, 190, 20)    # Золотой
COLOR_BANNER_BG: Final[tuple[int, int, int]] = (20, 20, 25)     # Темный графит
COLOR_TEXT_WHITE: Final[tuple[int, int, int]] = (250, 250, 250)
COLOR_ALERT_BG: Final[tuple[int, int, int]] = (20, 20, 210)     # Ярко-красный
COLOR_WARN_BG: Final[tuple[int, int, int]] = (10, 140, 240)     # Оранжевый
COLOR_CASH_BG: Final[tuple[int, int, int]] = (180, 130, 20)     # Золотистый

# Цвета статических зон
COLOR_ZONE_CASHIER: Final[tuple[int, int, int]] = (220, 120, 30)    # Сине-голубой
COLOR_ZONE_CUSTOMER: Final[tuple[int, int, int]] = (30, 180, 220)   # Желто-оранжевый
COLOR_ZONE_EXCLUSION: Final[tuple[int, int, int]] = (150, 100, 170) # Фиолетово-серый

CLASS_PERSON: Final[int] = 0
CLASS_BOTTLE: Final[int] = 39
CLASS_CUP: Final[int] = 41
CLASS_CELL_PHONE: Final[int] = 67

TRACKED_CLASSES: Final[list[int]] = [
    CLASS_PERSON,
    CLASS_BOTTLE,
    CLASS_CUP,
    CLASS_CELL_PHONE,
]


class DetectedBox(NamedTuple):
    """Структура для отрисовки детекции."""

    x_min: int
    y_min: int
    x_max: int
    y_max: int
    label: str
    confidence: float
    color: tuple[int, int, int]
    is_alert: bool = False


def draw_corner_rect(
    img: np.ndarray,
    pt1: tuple[int, int],
    pt2: tuple[int, int],
    color: tuple[int, int, int],
    thickness: int = 2,
    corner_len: int = 15,
) -> None:
    """Отрисовка технологичного Bounding Box с усиленными углами."""
    x1, y1 = pt1
    x2, y2 = pt2

    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness=1, lineType=cv2.LINE_AA)

    t = thickness
    cv2.line(img, (x1, y1), (x1 + corner_len, y1), color, t, cv2.LINE_AA)
    cv2.line(img, (x1, y1), (x1, y1 + corner_len), color, t, cv2.LINE_AA)
    cv2.line(img, (x2, y1), (x2 - corner_len, y1), color, t, cv2.LINE_AA)
    cv2.line(img, (x2, y1), (x2, y1 + corner_len), color, t, cv2.LINE_AA)
    cv2.line(img, (x1, y2), (x1 + corner_len, y2), color, t, cv2.LINE_AA)
    cv2.line(img, (x1, y2), (x1, y2 - corner_len), color, t, cv2.LINE_AA)
    cv2.line(img, (x2, y2), (x2 - corner_len, y2), color, t, cv2.LINE_AA)
    cv2.line(img, (x2, y2), (x2, y2 - corner_len), color, t, cv2.LINE_AA)


def draw_pill_badge(
    img: np.ndarray,
    text: str,
    org: tuple[int, int],
    bg_color: tuple[int, int, int],
    text_color: tuple[int, int, int] = COLOR_TEXT_WHITE,
    font_scale: float = 0.5,
) -> None:
    """Отрисовка контрастного информационного бейджа с фоном."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    thickness = 1
    (tw, th), baseline = cv2.getTextSize(text, font, font_scale, thickness)

    x, y = org
    pad_x, pad_y = 6, 4
    x1 = max(0, x - pad_x)
    y1 = max(0, y - th - pad_y)
    x2 = min(img.shape[1], x + tw + pad_x)
    y2 = min(img.shape[0], y + baseline + pad_y)

    cv2.rectangle(img, (x1, y1), (x2, y2), bg_color, -1, lineType=cv2.LINE_AA)
    cv2.rectangle(img, (x1, y1), (x2, y2), (255, 255, 255), 1, lineType=cv2.LINE_AA)

    cv2.putText(
        img,
        text,
        (x1 + pad_x, y2 - baseline - 1),
        font,
        font_scale,
        text_color,
        thickness,
        lineType=cv2.LINE_AA,
    )


def draw_static_zone(
    frame: np.ndarray,
    zone: NormalizedZone,
    color: tuple[int, int, int],
    label: str,
) -> None:
    """Отрисовка полупрозрачной статической зоны кассового узла."""
    h, w = frame.shape[:2]
    x1 = int(zone.x_min * w)
    y1 = int(zone.y_min * h)
    x2 = int(zone.x_max * w)
    y2 = int(zone.y_max * h)

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1, lineType=cv2.LINE_AA)

    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(
        frame,
        f"ZONE: {label}",
        (x1 + 6, y1 + 18),
        font,
        0.42,
        color,
        1,
        lineType=cv2.LINE_AA,
    )


def draw_hud_banner(
    frame: np.ndarray,
    timecode_sec: float,
    fps: float,
    fsm_state: str,
    verdict_text: str,
    badge_bg: tuple[int, int, int],
    motion_score: float,
    law_article: str = "",
) -> None:
    """Отрисовка полупрозрачного верхнего HUD-баннера мониторинга Vizi."""
    _h, w = frame.shape[:2]
    banner_height = 82

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_height), COLOR_BANNER_BG, -1)
    cv2.line(overlay, (0, banner_height), (w, banner_height), badge_bg, 2, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    font = cv2.FONT_HERSHEY_SIMPLEX

    # 1. Логотип и телеметрия
    cv2.putText(
        frame,
        "VIZI COMPLIANCE AI",
        (16, 26),
        font,
        0.58,
        (255, 255, 255),
        2,
        lineType=cv2.LINE_AA,
    )

    minutes = int(timecode_sec // 60)
    seconds = timecode_sec % 60
    tc_str = f"TC: {minutes:02d}:{seconds:04.1f}s | FPS: {fps:.1f} | TRAY SCORE: {motion_score:.0f}"
    cv2.putText(
        frame,
        tc_str,
        (16, 52),
        font,
        0.44,
        (180, 190, 200),
        1,
        lineType=cv2.LINE_AA,
    )

    # Ссылка на статью НПА РК
    if law_article:
        cv2.putText(
            frame,
            f"LAW: {law_article}",
            (16, 72),
            font,
            0.40,
            (255, 200, 100),
            1,
            lineType=cv2.LINE_AA,
        )

    # 2. Мгновенный вердикт безопасности
    verdict_badge_text = f" {verdict_text} "
    (vw, vh), vbase = cv2.getTextSize(verdict_badge_text, font, 0.60, 2)
    badge_x2 = w - 16
    badge_x1 = badge_x2 - vw - 14
    badge_y1 = 14
    badge_y2 = badge_y1 + vh + 16

    cv2.rectangle(
        frame, (badge_x1, badge_y1), (badge_x2, badge_y2), badge_bg, -1, lineType=cv2.LINE_AA
    )
    cv2.rectangle(
        frame, (badge_x1, badge_y1), (badge_x2, badge_y2), (255, 255, 255), 1, lineType=cv2.LINE_AA
    )
    cv2.putText(
        frame,
        verdict_badge_text,
        (badge_x1 + 6, badge_y2 - vbase - 3),
        font,
        0.60,
        COLOR_TEXT_WHITE,
        2,
        lineType=cv2.LINE_AA,
    )

    # Статус FSM
    fsm_str = f"FSM: {fsm_state}"
    (fw, _), _ = cv2.getTextSize(fsm_str, font, 0.44, 1)
    cv2.putText(
        frame,
        fsm_str,
        (badge_x1 - fw - 16, 44),
        font,
        0.44,
        (220, 220, 220),
        1,
        lineType=cv2.LINE_AA,
    )


class VideoOverlayAnnotator:
    """Генератор демонстрационного видео с зонами, HUD и детекциями."""

    def __init__(
        self,
        yolo_model: str | None = None,
        sample_fps: float = 1.0,
        buffer_size: int = 5,
        min_contour_area: float = 500.0,
        zones: BankDeskZones | None = None,
        use_vlm_judge: bool = True,
    ) -> None:
        weights = Path(__file__).resolve().parents[3] / "models" / "yolov8n.pt"
        self.yolo = YOLO(yolo_model or str(weights))
        self.analyzer = TemporalMotionAnalyzer(
            sample_fps=sample_fps,
            buffer_size=buffer_size,
            min_contour_area=min_contour_area,
        )
        self.zones = zones or BankDeskZones()
        self.sample_fps = sample_fps
        self.use_vlm_judge = use_vlm_judge
        self.vlm_judge = VLMComplianceJudge() if use_vlm_judge else None

    def render(self, input_video: str | Path, output_video: str | Path) -> Path:
        """Потоковая обработка с наложением зон, HUD и конвертацией в H.264."""
        in_path = Path(input_video)
        out_path = Path(output_video)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if not in_path.is_file():
            raise FileNotFoundError(f"Файл не найден: {in_path}")

        cap = cv2.VideoCapture(str(in_path))
        if not cap.isOpened():
            raise ValueError(f"Не удалось открыть видеофайл: {in_path}")

        raw_temp_path = out_path.with_name(f"_raw_{out_path.name}")
        try:
            self._process_and_write(cap, in_path.name, raw_temp_path)
            self._transcode_to_web_h264(raw_temp_path, out_path)
            return out_path
        finally:
            cap.release()
            if raw_temp_path.is_file():
                raw_temp_path.unlink(missing_ok=True)

    def _transcode_to_web_h264(self, source_path: Path, target_path: Path) -> None:
        """Транскодирование в веб-совместимый H.264 MP4 c movflags faststart."""
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            logger.warning("ffmpeg не найден, сохраняем исходный файл видео")
            shutil.move(str(source_path), str(target_path))
            return

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(source_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-movflags",
            "+faststart",
            str(target_path),
        ]
        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
            )
        except Exception as exc:
            logger.warning("Ошибка транскодирования ffmpeg (%s), используем прямой вывод", exc)
            if not target_path.is_file():
                shutil.copyfile(str(source_path), str(target_path))

    def _process_and_write(
        self,
        cap: cv2.VideoCapture,
        video_name: str,
        out_path: Path,
    ) -> Path:
        video_fps = float(cap.get(cv2.CAP_PROP_FPS))
        if video_fps <= 0 or np.isnan(video_fps):
            video_fps = 25.0

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        logger.info(
            "Старт рендеринга: %s (%dx%d, %.1f FPS, %d кадров)",
            video_name,
            width,
            height,
            video_fps,
            total_frames,
        )

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, video_fps, (width, height))
        if not writer.isOpened():
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            writer = cv2.VideoWriter(str(out_path), fourcc, video_fps, (width, height))

        sample_step = max(1, round(video_fps / self.sample_fps))
        gray_buffer: deque[np.ndarray] = deque(maxlen=self.analyzer.buffer_size)

        fsm = BankComplianceFSM()

        current_boxes: list[DetectedBox] = []
        current_roi_bbox: BoundingBox | None = None
        current_fsm_state = "COMPLIANT"
        current_verdict = "OK: COMPLIANT"
        current_badge_bg = COLOR_PERSON
        current_motion_score = 0.0
        current_law = "NBRK Rule 231"

        vlm_checked = False
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            timecode_sec = round(frame_idx / video_fps, 2)

            if frame_idx % sample_step == 0:
                gray_proc = self.analyzer._preprocess_for_motion(frame)
                gray_buffer.append(gray_proc)

                current_boxes.clear()
                current_roi_bbox = None

                if len(gray_buffer) >= 2:
                    median_bg = self.analyzer._compute_median_background(gray_buffer)
                    motion_res = self.analyzer._detect_motion(gray_proc, median_bg)

                    if motion_res.has_motion and motion_res.roi_bbox is not None:
                        current_motion_score = motion_res.motion_score
                        scale_x = width / float(self.analyzer.proc_w)
                        scale_y = height / float(self.analyzer.proc_h)
                        current_roi_bbox = BoundingBox(
                            x_min=max(0, int(motion_res.roi_bbox.x_min * scale_x) - 45),
                            y_min=max(0, int(motion_res.roi_bbox.y_min * scale_y) - 45),
                            x_max=min(width, int(motion_res.roi_bbox.x_max * scale_x) + 45),
                            y_max=min(height, int(motion_res.roi_bbox.y_max * scale_y) + 45),
                        )
                    else:
                        current_motion_score = 0.0

                # Детекция YOLOv8n
                res_yolo = self.yolo(frame, classes=TRACKED_CLASSES, verbose=False)[0]

                # 1. Извлечение людей и спектрально-размерная классификация ролей
                person_boxes = [
                    ([int(v) for v in b.xyxy[0].tolist()], float(b.conf[0]))
                    for b in res_yolo.boxes
                    if int(b.cls[0]) == CLASS_PERSON
                ]
                classified_people = filter_reflection_and_assign_roles(
                    person_boxes, (height, width)
                )

                cashier_present = any(p.role == "CASHIER" for p in classified_people)
                customer_at_desk = any(
                    p.role == "CUSTOMER" and is_customer_at_desk(p.box, (height, width))
                    for p in classified_people
                )
                customer_count = sum(
                    1
                    for p in classified_people
                    if p.role == "CUSTOMER" and is_customer_at_desk(p.box, (height, width))
                )
                visitor_in_room_count = sum(
                    1
                    for p in classified_people
                    if p.role in (
                        "VISITOR_IN_CASH_ROOM",
                        "UNAUTHORIZED_IN_CASH_ROOM",
                        "UNAUTHORIZED_ACCESS",
                    )
                )

                # 2. Детекция запрещенных предметов с фильтрацией стационарных приборов
                cashier_box = next((p.box for p in classified_people if p.role == "CASHIER"), None)
                forbidden_items: list[str] = []
                forbidden_boxes: list[tuple[list[int], str, float]] = []
                for b in res_yolo.boxes:
                    cls_id = int(b.cls[0])
                    conf = float(b.conf[0])
                    coords = [int(v) for v in b.xyxy[0].tolist()]
                    if cls_id in (CLASS_CELL_PHONE, CLASS_CUP, CLASS_BOTTLE) and conf >= 0.35:
                        if cls_id == CLASS_CELL_PHONE and not is_real_phone_violation(
                            coords, (height, width), current_motion_score, cashier_box
                        ):
                            continue
                        item_map = {
                            CLASS_CELL_PHONE: "smartphone",
                            CLASS_CUP: "cup",
                            CLASS_BOTTLE: "bottle",
                        }
                        name = item_map[cls_id]
                        forbidden_items.append(name)
                        forbidden_boxes.append((coords, name, conf))

                # 3. VLM проверка удостоверения личности при необходимости
                if (
                    not vlm_checked
                    and self.vlm_judge
                    and should_trigger_id_verification(
                        timecode_sec, cashier_present, customer_at_desk
                    )
                ):
                    vlm_res = self.vlm_judge.judge_id_verification(frame)
                    fsm.feed_vlm_id_verdict(vlm_res)
                    vlm_checked = True

                # 4. Обновление FSM
                detections = FrameDetections(
                    timecode_sec=timecode_sec,
                    cashier_present=cashier_present,
                    customer_present=customer_at_desk,
                    customer_count=customer_count,
                    visitor_in_room_count=visitor_in_room_count,
                    exchange_tray_motion_score=current_motion_score,
                    tray_has_cash_movement=(current_motion_score > 3000),
                    forbidden_items=forbidden_items,
                    full_frame=frame,
                )
                step_violations = fsm.update(detections)

                # 5. Dynamic State Promotion: формирование Bounding Boxes людей
                for p in classified_people:
                    disp_label, disp_color = get_person_display_attributes(
                        role=p.role,
                        confidence=p.confidence,
                        is_customer_at_desk_flag=is_customer_at_desk(p.box, (height, width)),
                        id_verified=fsm.id_verified,
                        box=p.box,
                        frame_shape=(height, width),
                    )
                    is_alert = (disp_color == COLOR_VIOLATION)
                    current_boxes.append(
                        DetectedBox(
                            x_min=p.box[0],
                            y_min=p.box[1],
                            x_max=p.box[2],
                            y_max=p.box[3],
                            label=disp_label,
                            confidence=p.confidence,
                            color=disp_color,
                            is_alert=is_alert,
                        )
                    )

                # Bounding Boxes запрещенных предметов
                for coords, item_name, conf in forbidden_boxes:
                    current_boxes.append(
                        DetectedBox(
                            x_min=coords[0],
                            y_min=coords[1],
                            x_max=coords[2],
                            y_max=coords[3],
                            label=f"[!] {item_name.upper()}: {conf:.2f}",
                            confidence=conf,
                            color=COLOR_PHONE,
                            is_alert=True,
                        )
                    )

                if step_violations:
                    top_v = step_violations[0]
                    current_fsm_state = top_v.type
                    current_verdict = f"ALERT: {top_v.type}"
                    current_badge_bg = COLOR_ALERT_BG
                    current_law = top_v.law
                elif current_motion_score > 3000:
                    if fsm.session_mode == SessionType.INTERNAL_OPERATION:
                        current_fsm_state = "INTERNAL_OPERATION"
                        current_verdict = "INTERNAL COUNTING"
                        current_badge_bg = COLOR_CASH_BG
                        current_law = "Rule 231 cl. 22"
                    elif fsm.id_verified:
                        current_fsm_state = "TRANSACTION_IN_PROGRESS"
                        current_verdict = "TRANSACTION: VERIFIED"
                        current_badge_bg = COLOR_CASH_BG
                        current_law = "Rule 231 cl. 19, 20"
                    else:
                        current_fsm_state = "CASH_EXCHANGE"
                        current_verdict = "CASH EXCHANGE ACTIVE"
                        current_badge_bg = COLOR_CASH_BG
                        current_law = "Rule 231 cl. 18, 20"
                else:
                    if fsm.session_mode == SessionType.INTERNAL_OPERATION:
                        current_fsm_state = "INTERNAL_MODE"
                        current_verdict = "INTERNAL AUDIT"
                        current_badge_bg = COLOR_CLIENT_VERIFIED
                        current_law = "Rule 231 NB RK"
                    elif fsm.id_verified:
                        current_fsm_state = "COMPLIANT_VERIFIED"
                        current_verdict = "OK: ID VERIFIED"
                        current_badge_bg = COLOR_CLIENT_VERIFIED
                        current_law = "Rule 231 NB RK"
                    else:
                        current_fsm_state = "COMPLIANT"
                        current_verdict = "OK: COMPLIANT"
                        current_badge_bg = COLOR_PERSON
                        current_law = "Rule 231 NB RK"

            # --- Отрисовка элементов на кадре ---
            draw_frame = frame.copy()

            # 1. Статические нормативные зоны
            draw_static_zone(
                draw_frame, self.zones.cashier_zone, COLOR_ZONE_CASHIER, "CASHIER DESK"
            )
            draw_static_zone(
                draw_frame, self.zones.customer_zone, COLOR_ZONE_CUSTOMER, "CUSTOMER AREA"
            )
            draw_static_zone(
                draw_frame,
                self.zones.glass_door_exclusion,
                COLOR_ZONE_EXCLUSION,
                "GLASS DOOR (EXCLUSION)",
            )

            # 2. Зона лотка пересчета (Dynamic ROI)
            if current_roi_bbox is not None:
                draw_corner_rect(
                    draw_frame,
                    (current_roi_bbox.x_min, current_roi_bbox.y_min),
                    (current_roi_bbox.x_max, current_roi_bbox.y_max),
                    color=COLOR_ROI_CASH,
                    thickness=2,
                    corner_len=20,
                )
                roi_label = f"EXCHANGE TRAY (Score: {current_motion_score:.0f})"
                draw_pill_badge(
                    draw_frame,
                    roi_label,
                    (current_roi_bbox.x_min, max(85, current_roi_bbox.y_min - 6)),
                    bg_color=COLOR_CASH_BG,
                    text_color=COLOR_TEXT_WHITE,
                    font_scale=0.46,
                )

            # 3. Bounding Boxes объектов
            for d_box in current_boxes:
                draw_corner_rect(
                    draw_frame,
                    (d_box.x_min, d_box.y_min),
                    (d_box.x_max, d_box.y_max),
                    color=d_box.color,
                    thickness=3 if d_box.is_alert else 2,
                    corner_len=18,
                )
                badge_bg = COLOR_ALERT_BG if d_box.is_alert else COLOR_BANNER_BG
                draw_pill_badge(
                    draw_frame,
                    d_box.label,
                    (d_box.x_min, max(85, d_box.y_min - 6)),
                    bg_color=badge_bg,
                    text_color=COLOR_TEXT_WHITE,
                    font_scale=0.48,
                )

            # 4. Верхний нормативный HUD-баннер
            draw_hud_banner(
                frame=draw_frame,
                timecode_sec=timecode_sec,
                fps=video_fps,
                fsm_state=current_fsm_state,
                verdict_text=current_verdict,
                badge_bg=current_badge_bg,
                motion_score=current_motion_score,
                law_article=current_law,
            )

            writer.write(draw_frame)
            frame_idx += 1

        writer.release()
        return out_path
