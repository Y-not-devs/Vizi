"""Скрипт пакетной обработки тестовых видео с помощью TemporalMotionAnalyzer.

Извлекает активные сегменты (Rolling Median Temporal Window) и сохраняет кропы
высокого разрешения и метаданные в папку data/processed_segments/.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any

# Автоматическое добавление backend в sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.features.ai.motion_extractor import TemporalMotionAnalyzer


def save_segment_images(
    video_stem: str,
    segments: list[dict[str, Any]],
    output_dir: Path,
) -> list[dict[str, Any]]:
    """Сохранение base64 кадров и кропов в виде реальных JPEG-файлов на диск."""
    video_out = output_dir / video_stem
    crops_dir = video_out / "crops"
    full_dir = video_out / "full_frames"
    crops_dir.mkdir(parents=True, exist_ok=True)
    full_dir.mkdir(parents=True, exist_ok=True)

    metadata_records: list[dict[str, Any]] = []

    for idx, seg in enumerate(segments, start=1):
        timecode = seg["timecode_sec"]
        motion_score = seg["motion_score"]

        # Имена файлов с таймкодом
        crop_filename = f"{idx:02d}_crop_{timecode:.1f}s.jpg"
        full_filename = f"{idx:02d}_full_{timecode:.1f}s.jpg"

        crop_path = crops_dir / crop_filename
        full_path = full_dir / full_filename

        # Декодирование и сохранение кропа
        crop_bytes = base64.b64decode(seg["crop_base64"])
        crop_path.write_bytes(crop_bytes)

        # Декодирование и сохранение полного кадра
        full_bytes = base64.b64decode(seg["full_frame_base64"])
        full_path.write_bytes(full_bytes)

        metadata_records.append(
            {
                "index": idx,
                "timecode_sec": timecode,
                "motion_score": motion_score,
                "crop_file": str(crop_path.relative_to(output_dir)),
                "full_file": str(full_path.relative_to(output_dir)),
                "crop_bytes_size": len(crop_bytes),
            }
        )

    # Сохранение итогового json-манифеста по видео
    meta_path = video_out / "metadata.json"
    meta_path.write_text(
        json.dumps(
            {
                "video_name": video_stem,
                "total_active_segments": len(segments),
                "segments": metadata_records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return metadata_records


def process_videos(
    input_dir: Path,
    output_dir: Path,
    limit: int | None = None,
) -> None:
    """Пакетная обработка всех видео в директории."""
    if not input_dir.exists():
        print(f"[-] Ошибка: Директория не найдена: {input_dir}")
        sys.exit(1)

    extensions = ("*.mov", "*.mp4", "*.avi", "*.mkv")
    videos: list[Path] = []
    for ext in extensions:
        videos.extend(input_dir.glob(ext))
    videos = sorted(videos)

    if not videos:
        print(f"[-] В директории {input_dir} не найдено видеофайлов ({', '.join(extensions)})")
        sys.exit(1)

    total_count = len(videos)
    if limit is not None and limit > 0:
        videos = videos[:limit]
        print(f"[i] Ограничение выборки: обрабатываются первые {len(videos)} из {total_count} видео")
    else:
        print(f"[i] Найдено {total_count} видео для обработки")

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[i] Результаты (кропы и метаданные) сохраняются в: {output_dir}")

    analyzer = TemporalMotionAnalyzer(
        sample_fps=1.0,
        buffer_size=5,
        min_contour_area=500.0,
        max_active_segments=15,
    )

    total_start = time.perf_counter()
    summary: list[dict[str, Any]] = []

    for i, vid in enumerate(videos, start=1):
        print(f"\n[{i}/{len(videos)}] Обработка: {vid.name} ... ", end="", flush=True)
        vid_start = time.perf_counter()

        try:
            segments = analyzer.extract_active_segments(vid)
            vid_elapsed = time.perf_counter() - vid_start

            # Сохранение кропов в папку data/processed_segments/<video_name>
            save_segment_images(vid.stem, segments, output_dir)

            print(
                f"OK ({vid_elapsed:.2f}c) | активных сегментов для VLM: {len(segments)}"
            )

            summary.append(
                {
                    "video": vid.name,
                    "status": "success",
                    "elapsed_sec": round(vid_elapsed, 2),
                    "active_segments": len(segments),
                }
            )
        except Exception as exc:  # noqa: BLE001
            vid_elapsed = time.perf_counter() - vid_start
            print(f"ОШИБКА ({vid_elapsed:.2f}c): {exc}")
            summary.append(
                {
                    "video": vid.name,
                    "status": "error",
                    "error": str(exc),
                    "elapsed_sec": round(vid_elapsed, 2),
                }
            )

    total_elapsed = time.perf_counter() - total_start
    print("\n" + "=" * 60)
    print(f"[✓] Пакетная обработка завершена за {total_elapsed:.2f} сек.")
    print(f"[✓] Всего обработано видео: {len(summary)}")
    successful = [s for s in summary if s["status"] == "success"]
    total_segments = sum(s["active_segments"] for s in successful)
    print(f"[✓] Успешно: {len(successful)} / {len(summary)}")
    print(f"[✓] Суммарно выделено активных кропов для VLM: {total_segments}")
    print(f"[✓] Папка с результатами: {output_dir.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Пакетная обработка видео ForteWatch через TemporalMotionAnalyzer."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data" / "test_videos",
        help="Путь к папке с видео (по умолчанию: data/test_videos)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed_segments",
        help="Путь к папке для сохранения кропов (по умолчанию: data/processed_segments)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничить количество обрабатываемых видео (по умолчанию: все)",
    )

    args = parser.parse_args()
    process_videos(input_dir=args.input, output_dir=args.output, limit=args.limit)