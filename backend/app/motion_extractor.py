"""Удобный реэкспорт модуля motion_extractor."""

from app.features.ai.motion_extractor import (
    ActiveFrameSegment,
    BoundingBox,
    MotionDetectionResult,
    TemporalMotionAnalyzer,
)

__all__ = [
    "ActiveFrameSegment",
    "BoundingBox",
    "MotionDetectionResult",
    "TemporalMotionAnalyzer",
]
