"""ASGI service wiring with owned fake Docker and HTTP transport boundaries."""

import json
from pathlib import Path
from types import SimpleNamespace
import httpx
from fastapi.testclient import TestClient
from sandbox_manager.backend import SandboxEndpoint
from sandbox_manager.registry import Registry
from sandbox_manager.workspace_client import RemoteWorkspaces
from test.sandbox_manager.integration.support import (
    disable_health_monitor,
    patch_http_clients,
    service_config,
)
from test.sandbox_manager.integration.test_remote_catalog import full_bundle


def test_startup_native_acquire_catalog_file_and_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "default"))
    monkeypatch.setenv("LOG_ROOT", str(tmp_path / "logs"))
    import sandbox_manager.main as service

    requests = []
    current = [full_bundle(1)]
    layout = {
        name: str(tmp_path / "workspace" / name)
        for name in ("root", "shared", "sessions")
    }
    # RemoteWorkspaces uses the actual WorkspaceLayout contract.
    from dataclasses import fields
    from shared_libs.workspace_paths import WorkspaceLayout

    layout = {
        field.name: str(tmp_path / "workspace" / field.name)
        for field in fields(WorkspaceLayout)
    }

    def handle(request):
        requests.append((request.url.host, request.url.path))
        if request.url.host != "runtime.test":
            assert request.headers.get("Authorization") == "Bearer service"
        if request.url.path.endswith("/bundle"):
            return httpx.Response(200, json=current[0])
        if request.url.path.endswith("/authorize"):
            payload = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "mutation": request.method == "POST",
                    "payload": payload["payload"],
                },
            )
        if request.url.path == "/internal/v1/workspaces/allocate":
            return httpx.Response(
                200, json={"layout": layout, "path": layout.get("shared")}
            )
        if request.url.path == "/session" and request.method == "POST":
            assert "authorization" not in request.headers
            return httpx.Response(201, json={"id": "ses_pipeline", "title": "Pipeline"})
        if request.url.path == "/session/status":
            return httpx.Response(200, json={})
        if request.url.host == "runtime.test":
            return httpx.Response(200, json={"id": "ses_pipeline"})
        return httpx.Response(200, json={"ok": True})

    class Stream(httpx.AsyncByteStream):
        def __init__(self, content):
            self.content = content

        async def __aiter__(self):
            yield self.content

    def async_handle(request):
        response = handle(request)
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=Stream(response.content),
        )

    patch_http_clients(monkeypatch, handle, async_handle)
    disable_health_monitor(monkeypatch, service)
    config = service_config(tmp_path)
    registry = Registry(tmp_path / "registry.db")
    registry.initialize()
    workspaces = RemoteWorkspaces(config, tmp_path / "workspace", tmp_path / "state")

    class Docker:
        def ping(self):
            return True

        def close(self):
            pass

    class Backend:
        def __init__(self):
            self.registry = registry
            self.client = Docker()
            self.in_use = {}
            self._locks = {}
            self.removed = []

        async def acquire(self, aid, username):
            definition = self.agent_catalog.load(aid)
            workspaces.ensure_user_layout(aid, username)
            registry.upsert_agent(aid, str(definition.path), definition.image)
            registry.upsert_sandbox(
                sandbox_id="sbx_pipeline",
                agent_id=aid,
                username=username,
                container_id="container-pipeline",
                host_port=41000,
                status="ready",
                image_version=definition.image,
            )
            return SandboxEndpoint(
                "sbx_pipeline",
                "container-pipeline",
                41000,
                "http://runtime.test",
                False,
            )

        async def _acquire_locked(self, aid, username):
            return await self.acquire(aid, username)

        async def release(self, endpoint, **kwargs):
            pass

        async def inspect(self, aid, username):
            return SandboxEndpoint(
                "sbx_pipeline",
                "container-pipeline",
                41000,
                "http://runtime.test",
                False,
            )

        async def _get_container(self, cid):
            return SimpleNamespace(id=cid)

        def _verify_ownership(self, container, aid, username):
            pass

        async def _remove_owned(self, container):
            self.removed.append(container.id)

    backend = Backend()
    with TestClient(
        service.create_app(config, backend), headers={"Authorization": "Bearer service"}
    ) as client:
        assert client.get("/health/ready").status_code == 200
        result = client.post(
            "/session", json={"_cloud": {"agent_id": "agent-code", "username": "alice"}}
        )
        assert result.status_code == 201, result.text
        assert registry.get_session_route("ses_pipeline").agent_id == "agent-code"
        details = client.get("/internal/v1/sandboxes/sbx_pipeline").json()
        assert (
            isinstance(details["sessions"], list)
            and details["sessions"][0]["session_id"] == "ses_pipeline"
        )
        assert details["session_count"] == 1
        assert {
            "cpu_percent",
            "memory_bytes",
            "sampled_at",
            "configuration_version",
            "execution",
        } <= details.keys()
        preview = client.get("/internal/v1/sandboxes/sbx_pipeline/force-preview").json()
        assert {
            "preview_id",
            "execution",
            "sessions",
            "container_id",
            "activity_generation",
        } <= preview.keys()
        action = {"action": "quiesce", "request_id": "q1", "timeout": 0.1}
        assert (
            client.post(
                "/internal/v1/agents/agent-code/actions", json=action
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/session",
                json={"_cloud": {"agent_id": "agent-code", "username": "alice"}},
            ).status_code
            == 503
        )
        assert (
            client.post(
                "/internal/v1/agents/agent-code/actions", json=action
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/internal/v1/agents/agent-code/actions",
                json={"action": "apply", "request_id": "a1", "bundle": full_bundle(2)},
            ).status_code
            == 200
        )
        assert backend.removed == ["container-pipeline"]
        assert client.post(
            "/internal/v1/agents/agent-code/actions",
            json={"action": "verify", "request_id": "v1"},
        ).json()["verified"]
        assert backend.agent_catalog.load("agent-code").path.parent.name == "2"
        assert current[0]["version"] == 1
        assert (
            client.post(
                "/internal/v1/agents/agent-code/actions",
                json={"action": "resume", "request_id": "r-pending"},
            ).status_code
            == 409
        )
        current[0] = full_bundle(2)
        assert (
            client.post(
                "/internal/v1/agents/agent-code/actions",
                json={"action": "resume", "request_id": "r1"},
            ).status_code
            == 200
        )
        assert backend.agent_catalog.overrides == {}
        assert client.get("/session/ses_pipeline").status_code == 200
    workspaces.client.close()
    assert any(path.endswith("/bundle") for _, path in requests)
    assert any(path == "/internal/v1/workspaces/allocate" for _, path in requests)
