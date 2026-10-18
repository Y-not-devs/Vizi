import secrets
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings
from app.features.analysis import service
from app.features.analysis.schemas import AnalysisJob

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: Annotated[str | None, Depends(api_key_header)]) -> None:
    expected = get_settings().analysis_api_key
    if not expected:
        raise HTTPException(status_code=503, detail="Analysis API key is not configured")
    if not key or not secrets.compare_digest(key.encode(), expected.encode()):
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
