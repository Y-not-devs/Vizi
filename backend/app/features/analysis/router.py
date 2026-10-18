import secrets
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader

from app.core.config import get_settings
from app.features.analysis import service
from app.features.analysis.schemas import AnalysisJob

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    key: Annotated[str | None, Depends(api_key_header)] = None,
    api_key_query: Annotated[str | None, Query(alias="api_key")] = None,
) -> None:
    settings = get_settings()
    expected = settings.analysis_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="Analysis API key is not configured")
    if not settings.enable_auth and not key and not api_key_query:
        return
    token = key or api_key_query
    if not token or not secrets.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid API key")


router = APIRouter(prefix="/v1", tags=["analysis"], dependencies=[Depends(require_api_key)])


@router.post("/analyze", response_model=AnalysisJob, status_code=status.HTTP_202_ACCEPTED)
async def analyze(file: UploadFile, background_tasks: BackgroundTasks):
    job = await service.create_job(file)
    background_tasks.add_task(service.process_job, job.job_id)
    return job


@router.get("/jobs/{job_id}", response_model=AnalysisJob)
def get_job(job_id: str):
    return service.read_job(job_id)


@router.get("/jobs/{job_id}/annotated-video")
def get_annotated_video(job_id: str):
    directory = service.job_dir(job_id)
    video_path = directory / "annotated.mp4"
    if not video_path.is_file():
        raise HTTPException(status_code=404, detail="Annotated video not found")
    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=f"annotated_{job_id[:8]}.mp4",
    )
