import importlib
from fastapi.testclient import TestClient


class Router:
    def __init__(self, config):
        self.config = config

    async def acompletion(self, **payload):
        if payload.get("stream"):

            async def chunks():
                yield {"choices": [{"delta": {"content": "hello"}}]}

            return chunks()
        return {"choices": [{"message": {"content": "hello"}}]}


def test_authenticated_activation_streaming_and_draft_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "default"))
    monkeypatch.setenv("LOG_ROOT", str(tmp_path / "logs"))
    from model_gateway.main import create_app

    config = {
        "data_root": str(tmp_path / "gateway"),
        "log_root": str(tmp_path / "logs"),
        "service_token": "test-token",
    }
    client = TestClient(create_app(config, Router))
    assert client.get("/internal/v1/config/status").status_code == 401
    client.headers["Authorization"] = "Bearer test-token"
    assert client.get("/health/ready").status_code == 503
    payload = {
        "release_id": "r1",
        "version": 1,
        "configuration": {
            "model_list": [
                {"model_name": "test", "litellm_params": {"model": "openai/test"}}
            ]
        },
    }
    assert client.post("/internal/v1/config/validate", json=payload).status_code == 200
    assert client.post("/internal/v1/config/activate", json=payload).status_code == 200
    result = client.post("/v1/chat/completions", json={"model": "test", "stream": True})
    assert result.status_code == 200
    assert "hello" in result.text and "data: [DONE]" in result.text
    assert (
        client.post(
            "/cloud/admin/models/test-draft",
            json={
                "model": {
                    "id": "draft",
                    "provider": "openai",
                    "upstream_model": "draft",
                    "api_key": "private",
                }
            },
        ).json()["published"]
        is False
    )
    assert client.get("/internal/v1/config/status").json()["release_id"] == "r1"
    assert client.get("/v1/models").json()["data"][0]["id"] == "test"
