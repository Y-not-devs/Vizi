"""Isolated inference process; the API enforces the execution timeout."""

import json
import logging
import sys
from pathlib import Path

from app.core.config import get_settings
from app.features.ai.annotator import VideoOverlayAnnotator
from app.features.ai.auditor import BankComplianceAuditor

logger = logging.getLogger(__name__)


def analyze_video(path: Path) -> dict:
    settings = get_settings()
    auditor = BankComplianceAuditor(strict_vlm=True)
    auditor.vlm_judge.timeout_sec = settings.ai_timeout_seconds
    audit = auditor.audit_video(path)
    violations = [
        {
            "type": violation["type"],
            "timecode_sec": violation["timecode"],
            "description": violation["desc"],
            "rule": violation["law"],
            "evidence_frames": violation["evidence_frames"],
        }
        for violation in audit["violations"]
    ]

    has_annotated = False
    try:
        annotator = VideoOverlayAnnotator()
        annotated_target = path.parent / "annotated.mp4"
        annotator.render(path, annotated_target)
        has_annotated = annotated_target.is_file()
    except Exception:
        logger.exception("Не удалось сгенерировать аннотированное видео для %s", path)

    return {
        "verdict": "violation" if violations else "no_violation",
        "violations": violations,
        "processed_segments_count": audit["total_frames_checked"],
        "has_annotated_video": has_annotated,
    }


if __name__ == "__main__":
    result = analyze_video(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
