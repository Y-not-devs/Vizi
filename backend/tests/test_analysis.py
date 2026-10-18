import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.core.config import get_settings
from app.features.analysis import service

HEADERS = {"X-API-Key": "test-analysis-key"}


@pytest.fixture
def video_bytes(tmp_path):
    path = tmp_path / "sample.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
    assert writer.isOpened()
    for _ in range(20):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()
    return path.read_bytes()


def test_analysis_requires_api_key(client):
    assert client.post("/api/v1/analyze", files={"file": ("a.mp4", b"x")}).status_code == 401
    assert client.get("/api/v1/jobs/unknown").status_code == 401
    assert client.get("/api/v1/jobs/unknown", headers={"X-API-Key": "wrong"}).status_code == 401


def test_analysis_missing_server_key(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "analysis_api_key", "")
    assert client.get("/api/v1/jobs/unknown", headers=HEADERS).status_code == 503


@pytest.mark.parametrize(
    ("filename", "data", "expected"),
    [("bad.txt", b"x", 415), ("empty.mp4", b"", 422), ("bad.mp4", b"invalid", 422)],
)
def test_analysis_rejects_invalid_upload(client, filename, data, expected):
    response = client.post(
        "/api/v1/analyze", headers=HEADERS, files={"file": (filename, data, "video/mp4")}
    )
    assert response.status_code == expected
    assert not list(Path(get_settings().analysis_dir).glob("*/video.*"))


def test_analysis_upload_limit(client, monkeypatch, video_bytes):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    response = client.post(
        "/api/v1/analyze", headers=HEADERS, files={"file": ("sample.mp4", video_bytes)}
    )
    assert response.status_code == 413
    assert not list(Path(get_settings().analysis_dir).glob("*/video.*"))


@pytest.mark.parametrize("violation", [True, False])
def test_analysis_job_lifecycle(client, monkeypatch, video_bytes, violation):
    def inference(command, **kwargs):
        job_id = Path(command[-2]).parent.name
        assert service.read_job(job_id).status == "processing"
        assert kwargs["timeout"] == get_settings().analysis_timeout_seconds
        assert kwargs["env"]["AI_MODEL"] == get_settings().ai_model
        result = {
            "verdict": "violation" if violation else "no_violation",
            "violations": [
                {
                    "type": "PROHIBITED_ITEMS",
                    "timecode_sec": 1.0,
                    "description": "Phone detected",
                    "rule": "Existing rule reference",
                    "evidence_frames": [{"timestamp_sec": 1.0, "image_base64": "evidence"}],
                }
            ]
            if violation
            else [],
            "processed_segments_count": 2,
        }
        Path(command[-1]).write_text(json.dumps(result), encoding="utf-8")

    monkeypatch.setattr(service.subprocess, "run", inference)
    response = client.post(
        "/api/v1/analyze", headers=HEADERS, files={"file": ("sample.mp4", video_bytes)}
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    job_id = response.json()["job_id"]
    result = client.get(f"/api/v1/jobs/{job_id}", headers=HEADERS)
    assert result.status_code == 200
    data = result.json()
    assert data["status"] == "done"
    assert data["filename"] == "sample.mp4"
    assert data["total_duration_sec"] == 2
    assert data["verdict"] == ("violation" if violation else "no_violation")
    assert len(data["violations"]) == int(violation)
    if violation:
        assert data["violations"][0]["evidence_frames"][0]["image_base64"] == "evidence"
    service.recover_jobs()
    assert service.read_job(job_id).status == "done"


@pytest.mark.parametrize("timeout", [True, False])
def test_analysis_failure_is_not_a_clean_verdict(client, monkeypatch, video_bytes, timeout):
    def inference(command, **kwargs):
        if timeout:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(service.subprocess, "run", inference)
    response = client.post(
        "/api/v1/analyze", headers=HEADERS, files={"file": ("sample.mp4", video_bytes)}
    )
    job_id = response.json()["job_id"]
    data = client.get(f"/api/v1/jobs/{job_id}", headers=HEADERS).json()
    assert data["status"] == "failed"
    assert data["verdict"] is None
    assert data["error"]


def test_interrupted_analysis_is_recovered(client, monkeypatch, video_bytes):
    monkeypatch.setattr(service, "process_job", lambda job_id: None)
    response = client.post(
        "/api/v1/analyze", headers=HEADERS, files={"file": ("sample.mp4", video_bytes)}
    )
    job_id = response.json()["job_id"]
    assert service.read_job(job_id).status == "queued"
    service.recover_jobs()
    assert service.read_job(job_id).status == "failed"


@pytest.mark.parametrize("job_id", ["invalid", "0" * 32, "..%2Foutside"])
def test_analysis_unknown_job(client, job_id):
    assert client.get(f"/api/v1/jobs/{job_id}", headers=HEADERS).status_code == 404


def test_annotated_video_endpoint(client, monkeypatch, video_bytes):
    def inference(command, **_kwargs):
        result = {
            "verdict": "no_violation",
            "violations": [],
            "processed_segments_count": 1,
            "has_annotated_video": True,
        }
        res_file = Path(command[-1])
        res_file.write_text(json.dumps(result), encoding="utf-8")
        # create mock annotated video file
        (res_file.parent / "annotated.mp4").write_bytes(b"dummy_mp4_bytes")

    monkeypatch.setattr(service.subprocess, "run", inference)
    response = client.post(
        "/api/v1/analyze", headers=HEADERS, files={"file": ("sample.mp4", video_bytes)}
    )
    job_id = response.json()["job_id"]
    job_data = client.get(f"/api/v1/jobs/{job_id}", headers=HEADERS).json()
    assert job_data["status"] == "done"
    assert job_data["annotated_video_url"] == f"/v1/jobs/{job_id}/annotated-video"

    # Fetch annotated video with headers
    video_resp = client.get(f"/api/v1/jobs/{job_id}/annotated-video", headers=HEADERS)
    assert video_resp.status_code == 200
    assert video_resp.content == b"dummy_mp4_bytes"
    assert "video/mp4" in video_resp.headers["content-type"]

    # Fetch annotated video with query parameter api_key
    video_query_resp = client.get(
        f"/api/v1/jobs/{job_id}/annotated-video?api_key={HEADERS['X-API-Key']}"
    )
    assert video_query_resp.status_code == 200
    assert video_query_resp.content == b"dummy_mp4_bytes"
