"""Скрипт рендеринга аннотированного демонстрационного видео (Debug Overlay) для Vizi.

Интегрирует нормативный сценарный автомат (BankComplianceFSM по Правилам № 231 НБ РК):
1. Статичные полигоны зон кассового узла (Cashier, Customer, Glass Door Exclusion).
2. Динамическая зона активности лотка пересчета наличности (Exchange Tray ROI).
3. Bounding Boxes объектов с динамическим повышением роли (CASHIER, CLIENT: VERIFIED, UNAUTHORIZED, FORBIDDEN).
4. Юридически обоснованный HUD-баннер мониторинга безопасности вверху кадра.
5. Автоматическая веб-конвертация в H.264 MP4.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Резолв путей к модулям бэкенда
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.features.ai.annotator import VideoOverlayAnnotator

logging.getLogger("ultralytics").setLevel(logging.WARNING)
logger = logging.getLogger("vizi.render_annotated_video")


def resolve_video_path(path_arg: Path | str | None) -> Path | None:
    """Интеллектуальное разрешение пути к видеофайлу с поддержкой кириллицы/латиницы и нумерации."""
    candidates = [
        PROJECT_ROOT / "data" / "test_videos" / "X-1.mov",
        PROJECT_ROOT / "data" / "test_videos" / "Х-13.mov",
        PROJECT_ROOT / "data" / "test_videos" / "Х-14.mov",
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
        description="Vizi: Рендеринг нормативного видео с зонами, HUD и статьями Правил № 231."
    )
    parser.add_argument("video", nargs="?", type=Path, default=None)
    parser.add_argument("--output", "-o", type=Path, default=None)

    args = parser.parse_args()
    input_path = resolve_video_path(args.video)

    if input_path is None or not input_path.is_file():
        print(f"[-] Ошибка: Исходный видеофайл не найден: {args.video}!")
        sys.exit(1)

    output_dir = PROJECT_ROOT / "data" / "annotated_videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output or (output_dir / f"{input_path.stem}_compliance_annotated.mp4")

    print(f"\n[+] Исходное видео:       {input_path}")
    print(f"[+] Нормативное видео:    {out_path}")
    print("[+] Архитектура:          2 Статичные Зоны + FSM (Правила № 231) + VLM Judge\n")

    annotator = VideoOverlayAnnotator()
    annotator.render(input_path, out_path)

    print("\n" + "=" * 75)
    print("✅ НОРМАТИВНОЕ АННОТИРОВАННОЕ ВИДЕО СОЗДАНО ДЛЯ ЖЮРИ!")
    print(f"📁 Путь к файлу: {out_path.resolve()}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
