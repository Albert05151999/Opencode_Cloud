import asyncio
import json
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient


def app_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "default"))
    monkeypatch.setenv("LOG_ROOT", str(tmp_path / "log"))
    from file_service.main import create_app
    from file_service import coordination

    calls = []
    allowed = [True]
    original = httpx.AsyncClient

    def handle(request):
        calls.append(request.url.path)
        assert request.headers["Authorization"] == "Bearer service"
        if request.url.path.endswith("file-admission") and not allowed[0]:
            return httpx.Response(409, json={"detail": "deleting"})
        return httpx.Response(200, json={"allowed": True, "resources": None})

    monkeypatch.setattr(
        coordination,
        "internal_client",
        lambda config, module: original(
            base_url="http://operations.test",
            headers={"Authorization": "Bearer service"},
            transport=httpx.MockTransport(handle),
        ),
    )
    config = {
        "data_root": str(tmp_path / "files"),
        "log_root": str(tmp_path / "log"),
        "service_token": "service",
        "services": {"operations": "http://operations.test"},
        "settings": {},
    }
    return create_app(config), calls, allowed


def test_cleanup_replay_does_not_remove_new_data_and_conflict_is_rejected(
    tmp_path, monkeypatch
):
    app, calls, allowed = app_fixture(tmp_path, monkeypatch)
    client = TestClient(app, headers={"Authorization": "Bearer service"})
    assert (
        client.post(
            "/internal/v1/workspaces/allocate",
            json={"agent_id": "agent-code", "username": "alice"},
        ).status_code
        == 200
    )
    impact = client.get("/internal/v1/agents/agent-code/deletion-impact").json()
    body = {"request_id": "delete-1", "expected_fingerprint": impact["fingerprint"]}
    result = client.post("/internal/v1/agents/agent-code/cleanup", json=body)
    assert result.status_code == 200
    manager = app.state.workspaces
    layout = manager.ensure_user_layout("agent-code", "alice")
    fresh = layout.shared / "new.txt"
    fresh.write_text("new data")
    assert (
        client.post("/internal/v1/agents/agent-code/cleanup", json=body).json()
        == result.json()
    )
    assert fresh.read_text() == "new data"
    assert (
        client.post(
            "/internal/v1/agents/agent-code/cleanup", json={**body, "empty_only": True}
        ).status_code
        == 409
    )
    allowed[0] = False
    assert (
        client.post(
            "/internal/v1/workspaces/allocate",
            json={"agent_id": "agent-code", "username": "bob"},
        ).status_code
        == 409
    )
    assert "/internal/v1/cleanup-authorization" in calls
    assert "/internal/v1/file-admission" in calls


def test_upload_cleanup_are_serialized_and_fingerprint_is_rechecked(
    tmp_path, monkeypatch
):
    app, _, allowed = app_fixture(tmp_path, monkeypatch)
    from file_service.files import FileService

    original_upload = FileService.upload

    async def exercise():
        started, finish = asyncio.Event(), asyncio.Event()

        async def delayed(self, *args, **kwargs):
            started.set()
            await finish.wait()
            return await original_upload(self, *args, **kwargs)

        monkeypatch.setattr(FileService, "upload", delayed)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://files.test",
            headers={"Authorization": "Bearer service"},
        ) as client:
            await client.post(
                "/internal/v1/workspaces/allocate",
                json={"agent_id": "agent-code", "username": "alice"},
            )
            before = (
                await client.get("/internal/v1/agents/agent-code/deletion-impact")
            ).json()
            upload = asyncio.create_task(
                client.post(
                    "/cloud/files/upload",
                    data={"agent_id": "agent-code", "username": "alice"},
                    files={"file": ("sample.txt", b"content")},
                )
            )
            await asyncio.wait_for(started.wait(), 2)
            cleanup = asyncio.create_task(
                client.post(
                    "/internal/v1/agents/agent-code/cleanup",
                    json={
                        "request_id": "delete-race",
                        "expected_fingerprint": before["fingerprint"],
                    },
                )
            )
            await asyncio.sleep(0)
            assert not cleanup.done()
            finish.set()
            assert (await upload).status_code == 200
            assert (await cleanup).status_code == 409
            assert any(
                path.name == "sample.txt"
                for path in app.state.workspaces.workspace_root.rglob("*")
            )

    asyncio.run(exercise())


def test_interrupted_cleanup_receipt_refuses_replay(tmp_path, monkeypatch):
    app, _, _ = app_fixture(tmp_path, monkeypatch)
    journal = app.state.file_coordination
    payload = {
        "agent_id": "agent-code",
        "request_id": "interrupted",
        "expected_fingerprint": "old",
    }
    journal.begin("interrupted", payload)
    client = TestClient(app, headers={"Authorization": "Bearer service"})
    response = client.post(
        "/internal/v1/agents/agent-code/cleanup",
        json={"request_id": "interrupted", "expected_fingerprint": "old"},
    )
    assert response.status_code == 409
    assert "interrupted" in response.json()["detail"]


def test_admission_client_is_reused_and_closed_with_application(tmp_path, monkeypatch):
    from file_service import coordination
    from file_service.main import create_app

    instances = []

    class AdmissionClient:
        def __init__(self):
            self.paths = []
            self.closed = False

        async def get(self, path, params):
            self.paths.append(path)
            return httpx.Response(200, json={"allowed": True, "resources": None})

        async def aclose(self):
            self.closed = True

    def create_client(config, module):
        assert module == "operations"
        client = AdmissionClient()
        instances.append(client)
        return client

    monkeypatch.setattr(coordination, "internal_client", create_client)
    config = {
        "data_root": str(tmp_path / "files"),
        "log_root": str(tmp_path / "log"),
        "service_token": "service",
        "services": {"operations": "http://operations.test"},
        "settings": {},
    }
    app = create_app(config)
    with TestClient(app, headers={"Authorization": "Bearer service"}) as client:
        for username in ("alice", "bob"):
            response = client.post(
                "/internal/v1/workspaces/allocate",
                json={"agent_id": "agent-code", "username": username},
            )
            assert response.status_code == 200
        assert len(instances) == 1
        assert instances[0].paths == [
            "/internal/v1/file-admission",
            "/internal/v1/file-admission",
        ]
        assert not instances[0].closed
    assert instances[0].closed
