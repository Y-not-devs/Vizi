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
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.features.ai.auditor import BankComplianceAuditor
from app.features.ai.compliance_fsm import SessionType
from scripts.render_annotated_video import VideoOverlayAnnotator


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
        v_room = item.get("visitor_in_room_count", 0)
        c_count = item["customer_count"]
        if v_room > 0 and c_count > 0:
            customers = f"{c_count}+{v_room} пос."
        elif v_room > 0:
            customers = f"{v_room} посет."
        else:
            customers = f"{c_count} чел."
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
    session_mode = audit.get("session_mode", SessionType.CUSTOMER_SESSION)
    mode_label = (
        "ВНУТРЕННИЙ ПЕРЕСЧЕТ / ИНКАССАЦИЯ (Клиент отсутствует штатно)"
        if session_mode == SessionType.INTERNAL_OPERATION
        else "ОБСЛУЖИВАНИЕ КЛИЕНТА (CUSTOMER_SESSION)"
    )
    print(f"• Операционный режим FSM:            {mode_label}")

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


def resolve_video_path(path_arg: Path | str | None) -> Path | None:
    """Интеллектуальное разрешение пути к видеофайлу с поддержкой кириллицы/латиницы и нумерации."""
    candidates = [
        PROJECT_ROOT / "data" / "test_videos" / "Х-13.mov",
        PROJECT_ROOT / "data" / "test_videos" / "Х-14.mov",
        PROJECT_ROOT / "data" / "test_videos" / "X-1.mov",
    ]
    if path_arg is None:
        for c in candidates:
            if c.is_file():
                return c
        return None

    path = Path(path_arg)
    if path.is_file():
        return path

    test_videos_dir = PROJECT_ROOT / "data" / "test_videos"
    if not test_videos_dir.exists():
        return None

    # Нормализация для нечувствительности к кириллице 'Х' vs латинице 'X' и ведущим нулям (Х-01 -> X-1)
    def normalize_stem(stem: str) -> str:
        s = stem.replace("Х", "X").replace("х", "x").upper().strip()
        parts = s.split("-")
        if len(parts) == 2 and parts[1].isdigit():
            return f"{parts[0]}-{int(parts[1])}"
        return s

    norm_target = normalize_stem(path.stem)

    for f in sorted(test_videos_dir.iterdir()):
        if not f.is_file():
            continue
        if normalize_stem(f.stem) == norm_target:
            return f

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
    video_path = resolve_video_path(args.video)

    if video_path is None or not video_path.is_file():
        print(f"[-] Видеофайл не найден для аудита: {args.video}!")
        print("    Доступные видео в data/test_videos/:")
        test_dir = PROJECT_ROOT / "data" / "test_videos"
        if test_dir.is_dir():
            files = sorted(f.name for f in test_dir.glob("*.mov"))
            print(f"    {', '.join(files[:8])}...")
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
