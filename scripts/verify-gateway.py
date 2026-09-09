#!/usr/bin/env python3
"""Compare stage-14 gateway responses with a real OpenCode sandbox."""

from __future__ import annotations

import asyncio
import atexit
import json
import hashlib
import shutil
from dataclasses import replace
from pathlib import Path

import docker
import httpx
from app.config import load_config
from app.gateway import create_gateway_router
from app.main import create_app
from app.registry import Registry
from app.sandbox import LocalDockerBackend, sandbox_key
from app.workspace import WorkspaceManager


PROJECT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path("/tmp/cloud-agent-gateway-verification")
REPORT = PROJECT / "artifacts" / "gateway" / "report.json"
INSTANCE = "stage14-verification"


def remove_container(client: docker.DockerClient) -> None:
    name = f"cloud-agent-{sandbox_key('agent-code', 'alice')}"
    try:
        container = client.containers.get(name)
    except docker.errors.NotFound:
        return
    labels = container.attrs.get("Config", {}).get("Labels") or {}
    if labels.get("cloud.platform_instance") != INSTANCE:
        raise RuntimeError(f"refusing to remove non-test container {name}")
    container.remove(force=True)


async def verify() -> dict[str, object]:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)
    shutil.copytree(
        PROJECT / "agents" / "agent-code",
        TEST_ROOT / "agents" / "agent-code",
    )

    config = load_config(PROJECT / "config.cfg")
    config = replace(config, platform=replace(config.platform, instance_id=INSTANCE))
    registry = Registry(TEST_ROOT / "platform.db")
    registry.initialize()
    workspaces = WorkspaceManager(
        TEST_ROOT / "workspaces", TEST_ROOT / "state",
        runtime_uid=10001, runtime_gid=10001,
    )
    docker_client = docker.from_env()
    docker_client.ping()
    remove_container(docker_client)

    def cleanup() -> None:
        remove_container(docker_client)
        if TEST_ROOT.exists():
            shutil.rmtree(TEST_ROOT)

    atexit.register(cleanup)
    sandboxes = LocalDockerBackend(
        config, registry, workspaces, TEST_ROOT / "agents", client=docker_client
    )
    stripped_requests = []
    async def inspect_forwarded(request):
        if request.headers.get("content-type", "").startswith("application/json") and request.content:
            payload = json.loads(request.content)
            assert not isinstance(payload, dict) or "_cloud" not in payload
            stripped_requests.append({"method": request.method, "path": request.url.path})
    upstream = httpx.AsyncClient(trust_env=False, timeout=20, event_hooks={"request": [inspect_forwarded]})
    app = create_app(create_gateway_router(registry, sandboxes, upstream))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway.test"
    ) as gateway:
        created = await gateway.post(
            "/session",
            json={
                "_cloud": {"agent_id": "agent-code", "username": "alice"},
                "title": "stage14 golden session",
            },
        )
        assert 200 <= created.status_code < 300, created.text
        created_payload = created.json()
        session_id = created_payload["id"]
        route = registry.get_session_route(session_id)
        assert route is not None and route.username == "alice"
        endpoint = await sandboxes.acquire("agent-code", "alice")
        direct = httpx.AsyncClient(base_url=endpoint.base_url, trust_env=False, timeout=20)
        specification_response = await direct.get("/doc")
        specification_response.raise_for_status()
        specification = specification_response.json()
        frozen = PROJECT / "docs/upstream" / f"opencode-{config.opencode.expected_version}-openapi.json"
        if not frozen.exists():
            prior = json.loads((PROJECT / "artifacts/opencode/openapi.json").read_text())
            assert specification == prior, "candidate differs from previously inspected upstream artifact"
            frozen.parent.mkdir(parents=True, exist_ok=True)
            frozen.write_text(json.dumps(specification, indent=2) + "\n")
        assert specification == json.loads(frozen.read_text()), "upstream schema changed; review required before replacing frozen specification"
        spec_sha256 = hashlib.sha256(frozen.read_bytes()).hexdigest()

        workspace_file = TEST_ROOT / "workspaces" / "agent-code" / "alice" / "shared" / "golden.txt"
        workspace_file.write_text("stage14-file\n", encoding="utf-8")
        checks = [
            ("GET", "/session", None, True),
            ("GET", f"/session/{session_id}", None, False),
            ("GET", f"/session/{session_id}/message", None, False),
            ("POST", f"/session/{session_id}/message", {}, False),
            ("POST", f"/session/{session_id}/abort", {}, False),
            ("GET", "/file?path=shared", None, True),
            ("GET", "/file/content?path=shared/golden.txt", None, True),
            ("GET", "/mcp", None, True),
            ("GET", "/agent", None, True),
            ("GET", "/config/providers", None, True),
            ("GET", "/global/health", None, True),
        ]
        observed: list[dict[str, object]] = []
        for method, path, payload, explicit in checks:
            kwargs: dict[str, object] = {}
            if payload is not None:
                kwargs["json"] = payload
            if explicit:
                kwargs["headers"] = {
                    "X-Cloud-Agent-ID": "agent-code",
                    "X-Cloud-Username": "alice",
                    "X-Cloud-Request-ID": "stage14-golden",
                }
            direct_response = await direct.request(method, path, **({"json": payload} if payload is not None else {}))
            gateway_response = await gateway.request(method, path, **kwargs)
            assert gateway_response.status_code == direct_response.status_code, path
            assert gateway_response.content == direct_response.content, (
                path,
                direct_response.content[:1000],
                gateway_response.content[:1000],
            )
            assert gateway_response.headers.get("content-type") == direct_response.headers.get("content-type"), path
            observed.append({"method": method, "path": path, "status": gateway_response.status_code})
        direct_created = await direct.post("/session", json={"title": "delete golden"})
        proxied_created = await gateway.post("/session", json={"_cloud": {"agent_id": "agent-code", "username": "alice"}, "title": "delete golden"})
        assert direct_created.is_success and proxied_created.is_success
        assert direct_created.json().keys() == proxied_created.json().keys()
        direct_deleted = await direct.delete(f"/session/{direct_created.json()['id']}")
        proxied_deleted = await gateway.delete(f"/session/{proxied_created.json()['id']}")
        assert direct_deleted.is_success and proxied_deleted.status_code == direct_deleted.status_code
        assert proxied_deleted.content == direct_deleted.content
        observed.append({"method": "DELETE", "path": "/session/:id", "status": proxied_deleted.status_code})
        assert stripped_requests
        await direct.aclose()

    await upstream.aclose()
    report = {
        "result": "passed",
        "opencode_version": config.opencode.expected_version,
        "session_id": session_id,
        "golden_checks": observed,
        "frozen_spec_sha256": spec_sha256,
        "forwarded_json_requests_without_cloud_metadata": len(stripped_requests),
        "checks": [
            "POST /session strips _cloud and persists session routing",
            "direct and gateway status/body/content-type match",
            "session routes resolve without repeated cloud metadata",
            "non-session routes use explicit cloud headers",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    cleanup()
    atexit.unregister(cleanup)
    return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(verify()), indent=2))
