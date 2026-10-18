"""Видеоанализ кассовой дисциплины: YOLO, motion extraction, FSM и локальная VLM."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np
from ultralytics import YOLO

from app.features.ai.compliance_fsm import (
    LAW_ID_CHECK,
    BankComplianceFSM,
    BankDeskZones,
    ComplianceViolation,
    FrameDetections,
    SessionType,
    VLMComplianceJudge,
    filter_reflection_and_assign_roles,
    is_real_phone_violation,
    should_trigger_id_verification,
)
from app.features.ai.motion_extractor import TemporalMotionAnalyzer

# COCO Classes
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


def decode_base64_to_image(b64_str: str) -> np.ndarray:
    """Декодирование base64 строки напрямую в NumPy BGR-изображение в оперативной памяти."""
    buffer = base64.b64decode(b64_str)
    np_arr = np.frombuffer(buffer, dtype=np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Не удалось декодировать изображение из base64 в память")
    return image


class BankComplianceAuditor:
    """Анализатор кассовой безопасности Vizi."""

    def __init__(
        self,
        yolo_model: str | None = None,
        zones: BankDeskZones | None = None,
        use_vlm_judge: bool = True,
        strict_vlm: bool = False,
    ) -> None:
        weights = Path(__file__).resolve().parents[2] / "models" / "yolov8n.pt"
        self.yolo = YOLO(yolo_model or str(weights))
        self.analyzer = TemporalMotionAnalyzer(
            sample_fps=1.0,
            buffer_size=5,
            min_contour_area=500.0,
            max_active_segments=25,
        )
        self.zones = zones or BankDeskZones()
        self.use_vlm_judge = use_vlm_judge
        self.vlm_judge = VLMComplianceJudge(raise_on_error=strict_vlm) if use_vlm_judge else None

    def audit_video(self, video_path: str | Path) -> dict[str, Any]:
        """Полный юридический аудит видеозаписи по Правилам № 231 НБ РК."""
        path = Path(video_path)
        if not path.is_file():
            raise FileNotFoundError(f"Видеофайл не найден: {path}")

        start_t = time.perf_counter()
        active_segments = self.analyzer.extract_active_segments(path)

        fsm = BankComplianceFSM()
        all_violations: list[ComplianceViolation] = []
        frame_logs: list[dict[str, Any]] = []

        vlm_id_verdict: dict[str, Any] | None = None
        vlm_checked = False

        for seg in active_segments:
            timecode = float(seg["timecode_sec"])
            motion_score = float(seg["motion_score"])

            full_frame = decode_base64_to_image(seg["full_frame_base64"])
            h, w = full_frame.shape[:2]

            # Детекция YOLOv8n по всем целевым классам
            res = self.yolo(full_frame, classes=TRACKED_CLASSES, verbose=False)[0]

            cashier_present = False
            # 1. Спектрально-размерная классификация людей (Кассир, Клиент, Отражение)
            person_boxes = [
                ([int(v) for v in b.xyxy[0].tolist()], float(b.conf[0]))
                for b in res.boxes
                if int(b.cls[0]) == CLASS_PERSON
            ]
            classified_people = filter_reflection_and_assign_roles(person_boxes, (h, w))

            cashier_present = any(p.role == "CASHIER" for p in classified_people)
            customer_count = sum(1 for p in classified_people if p.role == "CUSTOMER")
            visitor_in_room_count = sum(
                1
                for p in classified_people
                if p.role
                in ("VISITOR_IN_CASH_ROOM", "UNAUTHORIZED_IN_CASH_ROOM", "UNAUTHORIZED_ACCESS")
            )

            # 2. Поиск запрещенных предметов с Motion-Gated фильтрацией стационарных приборов
            detected_forbidden_names: list[str] = []
            cashier_box = next((p.box for p in classified_people if p.role == "CASHIER"), None)
            for b in res.boxes:
                cls_id = int(b.cls[0])
                conf = float(b.conf[0])
                if cls_id in (CLASS_CELL_PHONE, CLASS_CUP, CLASS_BOTTLE) and conf >= 0.35:
                    box_xyxy = [int(v) for v in b.xyxy[0].tolist()]
                    if cls_id == CLASS_CELL_PHONE and not is_real_phone_violation(
                        box_xyxy, (h, w), motion_score, cashier_box
                    ):
                        continue  # стационарная офисная техника (сканер, телефонная база)
                    item_name = self.yolo.names[cls_id]
                    detected_forbidden_names.append(item_name)

            # Проверка смартфона в кропе только при достаточной уверенности и динамике
            if (
                "cell phone" not in detected_forbidden_names
                and seg.get("crop_base64")
                and motion_score >= 3000.0
            ):
                crop_frame = decode_base64_to_image(seg["crop_base64"])
                res_crop = self.yolo(crop_frame, classes=[CLASS_CELL_PHONE], verbose=False)[0]
                for cb in res_crop.boxes:
                    if float(cb.conf[0]) >= 0.50:
                        detected_forbidden_names.append("cell phone")
                        break

            # Формирование входного среза для FSM
            frame_input = FrameDetections(
                timecode=timecode,
                cashier_present=cashier_present,
                customer_count=customer_count,
                visitor_in_room_count=visitor_in_room_count,
                tray_motion_score=motion_score,
                detected_objects=detected_forbidden_names,
                full_frame_b64=seg["full_frame_base64"],
                crop_b64=seg["crop_base64"],
            )

            # Оценка FSM по Правилам № 231 / Правилам № 14
            step_violations = fsm.evaluate_frame(frame_input)
            all_violations.extend(step_violations)

            # Проверка VLM-судьей (п. 19 пп. 1 Правил № 231: проверка ID-карты)
            # Опрос VLM физически возможен при наличии пары "кассир + клиент / посетитель"
            if (
                self.vlm_judge
                and not vlm_checked
                and should_trigger_id_verification(
                    cashier_present=cashier_present,
                    customer_present=(customer_count > 0 or visitor_in_room_count > 0),
                    tray_motion_score=motion_score,
                    id_already_verified=vlm_checked,
                )
            ):
                vlm_checked = True
                vlm_id_verdict = self.vlm_judge.verify_id_presentation(
                    crop_base64=seg["crop_base64"],
                    timecode=timecode,
                )
                if vlm_id_verdict.get("id_presented"):
                    fsm.id_verified = True
                else:
                    violation = ComplianceViolation(
                        timecode=timecode,
                        type="ID_NOT_PRESENT",
                        law=LAW_ID_CHECK,
                        desc=vlm_id_verdict.get("details", "Документ не предъявлен"),
                        severity="HIGH",
                    )
                    step_violations.append(violation)
                    all_violations.append(violation)

            status_str = "NORMAL"
            if step_violations:
                status_str = f"VIOLATION ({len(step_violations)})"
            elif motion_score > 3000:
                status_str = "CASH_ACTIVITY"

            frame_logs.append(
                {
                    "timecode": timecode,
                    "cashier_present": cashier_present,
                    "customer_count": customer_count,
                    "visitor_in_room_count": visitor_in_room_count,
                    "motion_score": motion_score,
                    "forbidden_items": detected_forbidden_names,
                    "status": status_str,
                    "violations": [v.to_dict() for v in step_violations],
                }
            )

        elapsed = time.perf_counter() - start_t

        evidence = {seg["timecode_sec"]: seg["full_frame_base64"] for seg in active_segments}
        violations = [
            {
                **v.to_dict(),
                "evidence_frames": [
                    {"timestamp_sec": v.timecode, "image_base64": evidence[v.timecode]}
                ],
            }
            for v in all_violations
        ]
        return {
            "video_name": path.name,
            "video_path": str(path.resolve()),
            "elapsed_sec": round(elapsed, 2),
            "total_frames_checked": len(frame_logs),
            "violations_total": len(all_violations),
            "violations": violations,
            "vlm_id_check": vlm_id_verdict,
            "session_mode": fsm.session_mode or SessionType.INTERNAL_OPERATION,
            "frame_logs": frame_logs,
        }
