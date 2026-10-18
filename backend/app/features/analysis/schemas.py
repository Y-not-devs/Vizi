from typing import Literal

from pydantic import BaseModel


class EvidenceFrame(BaseModel):
    timestamp_sec: float
    image_base64: str


class Violation(BaseModel):
    type: str
    timecode_sec: float
    description: str
    rule: str
    evidence_frames: list[EvidenceFrame]


class AnalysisJob(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "done", "failed"]
    filename: str
    total_duration_sec: float
    verdict: Literal["violation", "no_violation"] | None = None
    violations: list[Violation] | None = None
    processing_time_sec: float | None = None
    processed_segments_count: int | None = None
    error: str | None = None
