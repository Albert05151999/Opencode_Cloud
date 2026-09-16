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


def test_model_timing_separates_local_preparation_sdk_wait_and_stream(tmp_path,monkeypatch):
    import asyncio
    import model_gateway.main as service
    rows=[]
    monkeypatch.setattr(service,'emit',lambda action,**fields:rows.append({'action':action,**fields}))
    class DelayedRouter(Router):
        async def acompletion(self,**payload):
            await asyncio.sleep(.02)
            async def chunks():
                await asyncio.sleep(.03)
                yield {'choices':[{'delta':{'content':'hello'}}]}
                await asyncio.sleep(.04)
            return chunks()
    app=service.create_app({'data_root':str(tmp_path/'data'),'log_root':str(tmp_path/'logs'),'service_token':'test'},DelayedRouter)
    client=TestClient(app,headers={'Authorization':'Bearer test'})
    app.state.gateway.activate({'release_id':'timing','version':1,'configuration':{'model_list':[{'model_name':'test','litellm_params':{'model':'openai/test'}}]}})
    response=client.post('/v1/chat/completions',json={'model':'test','stream':True})
    assert response.status_code==200 and '[DONE]' in response.text
    stages={row['stage']:row for row in rows}
    assert set(stages)=={'gateway_prepare','model_sdk_wait','model_first_chunk_wait','model_stream_transfer'}
    assert stages['model_sdk_wait']['duration_ms']>=15
    assert stages['model_first_chunk_wait']['duration_ms']>=25
    assert stages['model_stream_transfer']['duration_ms']>=35
    assert len({row['parent_span_id'] for row in rows})==1
    assert len({row['span_id'] for row in rows})==4
