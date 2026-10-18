import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.config import BACKEND_DIR, get_settings
from app.features.analysis.schemas import AnalysisJob

logger = logging.getLogger(__name__)
analysis_lock = threading.Lock()
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def job_dir(job_id: str) -> Path:
    try:
        normalized = UUID(job_id).hex
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return Path(get_settings().analysis_dir) / normalized


def write_job(job: AnalysisJob) -> None:
    directory = job_dir(job.job_id)
    temporary = directory / "job.tmp"
    temporary.write_text(job.model_dump_json(), encoding="utf-8")
    temporary.replace(directory / "job.json")


def read_job(job_id: str) -> AnalysisJob:
    path = job_dir(job_id) / "job.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Job not found")
    return AnalysisJob.model_validate_json(path.read_text(encoding="utf-8"))


def video_duration(path: Path) -> float:
    import cv2

    cap = cv2.VideoCapture(str(path))
    try:
        ok, _ = cap.read()
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not cap.isOpened() or not ok or fps <= 0:
            raise HTTPException(status_code=422, detail="Cannot decode video")
        return round(cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps, 2)
    finally:
        cap.release()


async def create_job(file: UploadFile) -> AnalysisJob:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        await file.close()
        raise HTTPException(status_code=415, detail="Unsupported video format")
    job_id = uuid4().hex
    directory = job_dir(job_id)
    directory.mkdir(parents=True)
    video = directory / ("video" + suffix)
    try:
        size = 0
        with video.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > get_settings().max_upload_mb * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="Video exceeds upload limit")
                output.write(chunk)
        if not size:
            raise HTTPException(status_code=422, detail="Video is empty")
        duration = await run_in_threadpool(video_duration, video)
        job = AnalysisJob(
            job_id=job_id,
            status="queued",
            filename=Path(file.filename).name,
            total_duration_sec=duration,
        )
        write_job(job)
        return job
    except BaseException:
        shutil.rmtree(directory)
        raise
    finally:
        await file.close()


def process_job(job_id: str) -> None:
    # A single inference process at a time keeps CPU/RAM use bounded.
    with analysis_lock:
        job = read_job(job_id)
        directory = job_dir(job_id)
        video = next(directory.glob("video.*"))
        result_file = directory / "result.json"
        job.status = "processing"
        write_job(job)
        started = time.perf_counter()
        try:
            settings = get_settings()
            env = {
                **os.environ,
                "AI_BASE_URL": settings.ai_base_url,
                "AI_API_KEY": settings.ai_api_key,
                "AI_MODEL": settings.ai_model,
                "AI_TIMEOUT_SECONDS": str(settings.ai_timeout_seconds),
            }
            env.pop("ANALYSIS_API_KEY", None)
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.features.analysis.runner",
                    str(video),
                    str(result_file),
                ],
                cwd=BACKEND_DIR,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=settings.analysis_timeout_seconds,
            )
            result = json.loads(result_file.read_text(encoding="utf-8"))
            job = AnalysisJob.model_validate({**job.model_dump(), **result, "status": "done"})
        except subprocess.TimeoutExpired:
            job.status = "failed"
            job.error = "Превышено время анализа видео"
        except Exception:
            logger.exception("Video analysis failed for job %s", job_id)
            job.status = "failed"
            job.error = "Не удалось выполнить анализ видео"
        job.processing_time_sec = round(time.perf_counter() - started, 2)
        write_job(job)


def recover_jobs() -> None:
    for path in Path(get_settings().analysis_dir).glob("*/job.json"):
        job = AnalysisJob.model_validate_json(path.read_text(encoding="utf-8"))
        if job.status in {"queued", "processing"}:
            job.status = "failed"
            job.error = "Анализ прерван перезапуском сервера. Загрузите видео повторно."
            write_job(job)
