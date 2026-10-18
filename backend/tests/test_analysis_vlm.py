import json

import httpx
import pytest

from app.features.ai.compliance_fsm import VLMComplianceJudge


@pytest.mark.parametrize("status,payload", [(503, {}), (200, {"id_presented": "false"})])
def test_strict_vlm_rejects_provider_errors(monkeypatch, status, payload):
    def response(self, url, **kwargs):
        return httpx.Response(
            status,
            json={"choices": [{"message": {"content": json.dumps(payload)}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", response)
    with pytest.raises(RuntimeError, match="Local VLM analysis failed"):
        VLMComplianceJudge(raise_on_error=True).verify_id_presentation("image", 1.0)


def test_strict_vlm_preserves_negative_result(monkeypatch):
    def response(self, url, **kwargs):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"id_presented": false}'}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", response)
    result = VLMComplianceJudge(raise_on_error=True).verify_id_presentation("image", 1.0)
    assert result["id_presented"] is False
