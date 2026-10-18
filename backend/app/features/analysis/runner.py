"""Isolated inference process; the API enforces the execution timeout."""

import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.features.ai.auditor import BankComplianceAuditor


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
    return {
        "verdict": "violation" if violations else "no_violation",
        "violations": violations,
        "processed_segments_count": audit["total_frames_checked"],
    }


if __name__ == "__main__":
    result = analyze_video(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
