"""Скрипт юридически обоснованной проверки кассовой дисциплины банка (ForteWatch).

Нормативная база: «Правила ведения кассовых операций в банках второго уровня РК» (Постановление № 231).

Архитектура (2 статичные зоны + FSM + VLM):
1. Зональный геометрический трекинг людей (YOLO: person) по зонам:
   - Cashier Zone: рабочее место кассира;
   - Customer Zone: клиентская зона перед окном/стеклом;
   - Exchange Zone: зона пересчета и передачи банкнот (лоток).
2. Сценарный автомат (BankComplianceFSM):
   - п. 14: Постороннее лицо в зоне обслуживания (customer_count > 1);
   - п. 22: Оставление рабочего места кассиром (cashier absent >= 3s);
   - п. 20: Пересчет денег в отсутствие клиента (customer_count == 0 & tray motion >= 2s);
   - п. 12: Запрещенные личные вещи/еда/напитки/смартфон на столе.
3. Таргетированный VLM-судья (VLMComplianceJudge):
   - п. 18: Проверка факта предъявления ID-карты/паспорта/eGov при первом контакте.
"""

from __future__ import annotations

import argparse
import base64
import logging
import sys
import time
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np

# Резолв sys.path для импорта модулей из backend/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from ultralytics import YOLO  # type: ignore[import-untyped]
except ImportError as exc:
    raise ImportError(
        "Библиотека ultralytics не найдена. Установите ее: uv add ultralytics"
    ) from exc

from app.features.ai.compliance_fsm import (
    BankComplianceFSM,
    BankDeskZones,
    ComplianceViolation,
    FrameDetections,
    VLMComplianceJudge,
    filter_reflection_and_assign_roles,
    should_trigger_id_verification,
)
from app.features.ai.motion_extractor import TemporalMotionAnalyzer

from scripts.render_annotated_video import VideoOverlayAnnotator

logging.getLogger("ultralytics").setLevel(logging.WARNING)
logger = logging.getLogger("fortewatch.compliance_detector")

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
    """Аудитор кассовой безопасности ForteWatch."""

    def __init__(
        self,
        yolo_model: str = "yolov8n.pt",
        zones: BankDeskZones | None = None,
        use_vlm_judge: bool = True,
    ) -> None:
        self.yolo = YOLO(yolo_model)
        self.analyzer = TemporalMotionAnalyzer(
            sample_fps=1.0,
            buffer_size=5,
            min_contour_area=500.0,
            max_active_segments=25,
        )
        self.zones = zones or BankDeskZones()
        self.use_vlm_judge = use_vlm_judge
        self.vlm_judge = VLMComplianceJudge() if use_vlm_judge else None

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

            # 2. Поиск запрещенных предметов
            detected_forbidden_names: list[str] = []
            for b in res.boxes:
                cls_id = int(b.cls[0])
                conf = float(b.conf[0])
                if cls_id in (CLASS_CELL_PHONE, CLASS_CUP, CLASS_BOTTLE) and conf >= 0.35:
                    item_name = self.yolo.names[cls_id]
                    detected_forbidden_names.append(item_name)

            # Также проверяем смартфон в кропе высокого разрешения, если в общем кадре пропущен
            if "cell phone" not in detected_forbidden_names and seg.get("crop_base64"):
                crop_frame = decode_base64_to_image(seg["crop_base64"])
                res_crop = self.yolo(crop_frame, classes=[CLASS_CELL_PHONE], verbose=False)[0]
                for cb in res_crop.boxes:
                    if float(cb.conf[0]) >= 0.35:
                        detected_forbidden_names.append("cell phone")
                        break

            # Формирование входного среза для FSM
            frame_input = FrameDetections(
                timecode=timecode,
                cashier_present=cashier_present,
                customer_count=customer_count,
                tray_motion_score=motion_score,
                detected_objects=detected_forbidden_names,
                full_frame_b64=seg["full_frame_base64"],
                crop_b64=seg["crop_base64"],
            )

            # Оценка FSM по Правилам № 231
            step_violations = fsm.evaluate_frame(frame_input)
            all_violations.extend(step_violations)

            # Проверка VLM-судьей (п. 19 пп. 1 Правил № 231: проверка ID-карты)
            # Опрос VLM физически возможен только при наличии пары "кассир + клиент"
            if (
                self.vlm_judge
                and not vlm_checked
                and should_trigger_id_verification(
                    cashier_present=cashier_present,
                    customer_present=(customer_count > 0),
                    tray_motion_score=motion_score,
                    id_already_verified=vlm_checked,
                )
            ):
                vlm_checked = True
                vlm_id_verdict = self.vlm_judge.verify_id_presentation(
                    crop_base64=seg["crop_base64"],
                    timecode=timecode,
                )

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
                    "motion_score": motion_score,
                    "forbidden_items": detected_forbidden_names,
                    "status": status_str,
                    "violations": [v.to_dict() for v in step_violations],
                }
            )

        elapsed = time.perf_counter() - start_t

        return {
            "video_name": path.name,
            "video_path": str(path.resolve()),
            "elapsed_sec": round(elapsed, 2),
            "total_frames_checked": len(frame_logs),
            "violations_total": len(all_violations),
            "violations": [v.to_dict() for v in all_violations],
            "vlm_id_check": vlm_id_verdict,
            "frame_logs": frame_logs,
        }


def print_compliance_table(logs: list[dict[str, Any]]) -> None:
    """Вывод структурированной таблицы соответствия по таймкодам."""
    print("\n" + "=" * 115)
    print("📋 ТАБЛИЦА ЗОНАЛЬНОГО МОНИТОРИНГА И НОРМАТИВНЫХ СОБЫТИЙ (ПРАВИЛА № 231 НБ РК)")
    print("=" * 115)
    header = (
        f"{'Timecode':<10} | {'Кассир':<8} | {'Клиенты':<8} | "
        f"{'Лоток (Score)':<14} | {'Предметы':<14} | {'Нормативный статус / Инцидент'}"
    )
    print(header)
    print("-" * 115)

    for item in logs:
        tc = f"{item['timecode']:.1f}s"
        cashier = "Присутств." if item["cashier_present"] else "ОТСУТСТВ."
        customers = f"{item['customer_count']} чел."
        score = f"{item['motion_score']:.0f}"
        items = ", ".join(item["forbidden_items"]) if item["forbidden_items"] else "—"

        violations = item["violations"]
        if violations:
            desc = f"[!] {violations[0]['law']}: {violations[0]['type']}"
        elif item["motion_score"] > 3000:
            desc = "🔍 Передача / пересчет наличности в лотке"
        else:
            desc = "✅ Штатный режим"

        print(
            f"{tc:<10} | {cashier:<8} | {customers:<8} | "
            f"{score:<14} | {items:<14} | {desc}"
        )
    print("=" * 115)


def print_legal_verdict(audit: dict[str, Any]) -> None:
    """Вывод официального юридического заключения безопасности."""
    print("\n" + "=" * 80)
    print(f"⚖️ ОФИЦИАЛЬНЫЙ АКТ ПРОВЕРКИ КАССОВОЙ БЕЗОПАСНОСТИ: {audit['video_name']}")
    print("   Основание: Постановление Правления НБ РК № 231")
    print("=" * 80)
    print(f"• Время анализа записи:             {audit['elapsed_sec']:.2f} сек.")
    print(f"• Проверено активных секунд:         {audit['total_frames_checked']}")
    print(f"• Зафиксировано нарушений НПА:       {audit['violations_total']}")

    violations: list[dict[str, Any]] = audit["violations"]
    if violations:
        print("\n🚨 ПЕРЕЧЕНЬ ЗАФИКСИРОВАННЫХ НАРУШЕНИЙ ПРАВИЛ № 231:")
        by_law: dict[str, list[dict[str, Any]]] = {}
        for v in violations:
            by_law.setdefault(v["law"], []).append(v)

        for law, v_list in by_law.items():
            first_v = v_list[0]
            timecodes = ", ".join(f"{v['timecode']:.1f}s" for v in v_list)
            print(f"\n   [!] {law} ({first_v['type']}):")
            print(f"       Суть: {first_v['desc']}")
            print(f"       Таймкоды фиксации: [ {timecodes} ]")
            print(f"       Уровень критичности: {first_v['severity']}")
    else:
        print("\n✅ Нарушений пунктов 12, 14, 20, 22 Правил № 231 не выявлено.")

    # Вывод вердикта VLM-судьи
    vlm_verdict = audit.get("vlm_id_check")
    if vlm_verdict:
        print("\n🔍 ВЕРДИКТ VLM-СУДЬИ (Пункт 19 пп. 1 — Проверка документа/ID перед передачей денег):")
        status_vlm = "ПОДТВЕРЖДЕНО" if vlm_verdict.get("id_presented") else "НАРУШЕНИЕ"
        print(f"   Статус: [{status_vlm}] (Уверенность: {vlm_verdict.get('confidence', 0.0):.2f})")
        print(f"   Экспертиза VLM: {vlm_verdict.get('details', '—')}")
    else:
        print("\n🔍 VLM-СУДЬЯ (Пункт 19 пп. 1 — Проверка документа/ID):")
        print("   Статус: [ОПТИМИЗАЦИЯ FSM — ОПРОС НЕ ТРЕБУЕТСЯ]")
        print("   Причина: Нет субъектов взаимодействия (отсутствует пара «кассир + клиент»). 0 вызовов VLM.")

    print("=" * 80 + "\n")


def find_default_video() -> Path | None:
    """Поиск первого видео для аудита."""
    candidates = [
        PROJECT_ROOT / "data" / "test_videos" / "Х-13.mov",
        PROJECT_ROOT / "data" / "test_videos" / "Х-22.mov",
        PROJECT_ROOT / "data" / "test_videos" / "X-1.mov",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ForteWatch: Нормативный аудит кассовой безопасности (2 зоны + FSM + VLM)."
    )
    parser.add_argument("video", nargs="?", type=Path, default=None)
    parser.add_argument("--no-vlm", action="store_true", help="Отключить опрос VLM-судьи")
    parser.add_argument(
        "--no-video",
        action="store_true",
        help="Отключить автоматический рендеринг визуального видео (по умолчанию включен)",
    )
    parser.add_argument(
        "--output-video",
        "-o",
        type=Path,
        default=None,
        help="Путь для сохранения видео (по умолчанию: data/annotated_videos/<stem>_compliance_annotated.mp4)",
    )

    args = parser.parse_args()
    video_path = args.video or find_default_video()

    if video_path is None or not video_path.is_file():
        print("[-] Видеофайл не найден для аудита!")
        sys.exit(1)

    print(f"\n[+] Запуск аудита кассового узла: {video_path.name}")
    auditor = BankComplianceAuditor(use_vlm_judge=not args.no_vlm)

    audit_result = auditor.audit_video(video_path)

    # 1. Таблица зонального трекинга
    print_compliance_table(audit_result["frame_logs"])

    # 2. Юридически обоснованный вердикт со статьями НПА РК
    print_legal_verdict(audit_result)

    # 3. ВСЕГДА генерируем визуализированное видео для жюри и службы безопасности
    if not args.no_video:
        output_dir = PROJECT_ROOT / "data" / "annotated_videos"
        output_dir.mkdir(parents=True, exist_ok=True)
        out_video_path = args.output_video or (
            output_dir / f"{video_path.stem}_compliance_annotated.mp4"
        )
        print(f"[🎬] Генерация аннотированного видео с HUD и зонами: {out_video_path.name}...")
        annotator = VideoOverlayAnnotator(zones=auditor.zones)
        annotator.render(video_path, out_video_path)

        print("\n" + "=" * 80)
        print("🎥 АННОТИРОВАННОЕ ВИДЕО С ПОЛНОЙ ВИЗУАЛИЗАЦИЕЙ УСПЕШНО СОХРАНЕНО:")
        print(f"   Файл: {out_video_path.resolve()}")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
