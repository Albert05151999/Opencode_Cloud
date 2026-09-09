from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest
from app.gateway import create_gateway_router
from app.main import create_app
from app.registry import Registry
from app.sandbox import SandboxEndpoint, SandboxError, sandbox_key


class FakeSandboxes:
    def __init__(self, registry: Registry, *, error: str | None = None) -> None:
        self.registry = registry
        self.error = error
        self.calls: list[tuple[str, str]] = []
        self.releases: list[SandboxEndpoint] = []

    async def release(self, endpoint: SandboxEndpoint, *, activity_persisted=False) -> None:
        self.releases.append(endpoint)

    async def acquire(self, agent_id: str, username: str) -> SandboxEndpoint:
        self.calls.append((agent_id, username))
        if self.error is not None:
            raise SandboxError(self.error)
        key = sandbox_key(agent_id, username)
        sandbox_id = f"sbx_{key}"
        self.registry.upsert_agent(agent_id, f"/agents/{agent_id}", "runtime:test")
        self.registry.upsert_sandbox(
            sandbox_id=sandbox_id,
            agent_id=agent_id,
            username=username,
            container_id=f"container-{key}",
            host_port=41000,
            status="ready",
            image_version="runtime:test",
        )
        return SandboxEndpoint(
            sandbox_id,
            f"container-{key}",
            41000,
            "http://sandbox.test:41000",
            False,
        )


class OneChunkStream(httpx.AsyncByteStream):
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def __aiter__(self):
        yield self.content


class Harness:
    def __init__(
        self,
        registry: Registry,
        handler: Callable[[httpx.Request], httpx.Response],
        *,
        sandbox_error: str | None = None,
    ) -> None:
        self.registry = registry
        self.seen: list[httpx.Request] = []
        self.sandboxes = FakeSandboxes(registry, error=sandbox_error)

        def capture(request: httpx.Request) -> httpx.Response:
            self.seen.append(request)
            response = handler(request)
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                stream=OneChunkStream(response.content),
            )

        self.upstream = httpx.AsyncClient(transport=httpx.MockTransport(capture))
        self.app = create_app(
            create_gateway_router(registry, self.sandboxes, self.upstream)
        )

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://gateway.test",
        ) as client:
            return await client.request(method, url, **kwargs)

    async def close(self) -> None:
        await self.upstream.aclose()


def run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    value = Registry(tmp_path / "gateway.db")
    value.initialize()
    return value


def ok_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "POST" and request.url.path == "/session":
        return httpx.Response(201, json={"id": "ses_created", "title": "kept"})
    return httpx.Response(200, json={"ok": True})


def bind_session(
    registry: Registry,
    *,
    session_id: str = "ses_known",
    agent_id: str = "agent-code",
    username: str = "alice",
) -> None:
    key = sandbox_key(agent_id, username)
    sandbox_id = f"sbx_{key}"
    registry.upsert_agent(agent_id, f"/agents/{agent_id}", "runtime:test")
    registry.upsert_sandbox(
        sandbox_id=sandbox_id,
        agent_id=agent_id,
        username=username,
        container_id=f"container-{key}",
        host_port=41000,
        status="ready",
        image_version="runtime:test",
    )
    registry.record_session(
        session_id, sandbox_id, agent_id, username, f"sessions/{session_id}"
    )


def test_post_session_strips_cloud_preserves_native_fields_and_records(
    registry: Registry,
) -> None:
    harness = Harness(registry, ok_handler)

    async def scenario() -> httpx.Response:
        try:
            return await harness.request(
                "POST",
                "/session",
                json={
                    "_cloud": {
                        "agent_id": "agent-code",
                        "username": "alice",
                        "session_workspace": "projects/demo",
                    },
                    "title": "native title",
                    "agent": "build",
                    "parts": [{"type": "text", "text": "hello"}],
                },
            )
        finally:
            await harness.close()

    response = run(scenario())
    assert response.status_code == 201
    assert harness.sandboxes.calls == [("agent-code", "alice")]
    assert json.loads(harness.seen[0].content) == {
        "title": "native title",
        "agent": "build",
        "parts": [{"type": "text", "text": "hello"}],
    }
    route = registry.get_session_route("ses_created")
    assert route is not None
    assert (route.agent_id, route.username, route.workspace_relpath) == (
        "agent-code",
        "alice",
        "projects/demo",
    )


def test_get_routes_from_cloud_headers_and_removes_them(registry: Registry) -> None:
    harness = Harness(registry, ok_handler)

    async def scenario() -> httpx.Response:
        try:
            return await harness.request(
                "GET",
                "/session",
                headers={
                    "X-Cloud-Agent-ID": "agent-code",
                    "X-Cloud-Username": "alice",
                    "X-Cloud-Request-ID": "req-1",
                    "X-Native": "kept",
                },
            )
        finally:
            await harness.close()

    assert run(scenario()).status_code == 200
    assert harness.sandboxes.calls == [("agent-code", "alice")]
    upstream_headers = harness.seen[0].headers
    assert upstream_headers["x-native"] == "kept"
    assert "x-cloud-agent-id" not in upstream_headers
    assert "x-cloud-username" not in upstream_headers
    assert upstream_headers["x-cloud-request-id"] == "req-1"


def test_v2_session_envelope_is_preserved_and_registered(registry: Registry) -> None:
    def handler(request):
        assert "_cloud" not in json.loads(request.content)
        return httpx.Response(200, json={"data": {"id": "ses_v2", "title": "native"}})
    harness = Harness(registry, handler)
    async def scenario():
        try:
            return await harness.request("POST", "/api/session", json={"_cloud": {"agent_id": "agent-code", "username": "alice"}})
        finally:
            await harness.close()
    response = run(scenario())
    assert response.json() == {"data": {"id": "ses_v2", "title": "native"}}
    assert registry.get_session_route("ses_v2").username == "alice"


@pytest.mark.parametrize("path", ["/session/ses_known/message", "/api/session/ses_known"])
def test_registered_session_routes_without_metadata(registry: Registry, path: str) -> None:
    bind_session(registry)
    harness = Harness(registry, ok_handler)

    async def scenario() -> httpx.Response:
        try:
            return await harness.request("GET", path)
        finally:
            await harness.close()

    assert run(scenario()).status_code == 200
    assert harness.sandboxes.calls == [("agent-code", "alice")]


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        (
            {"X-Cloud-Agent-ID": "agent-code", "X-Cloud-Username": "alice"},
            200,
        ),
        (
            {"X-Cloud-Agent-ID": "agent-data", "X-Cloud-Username": "alice"},
            409,
        ),
        (
            {"X-Cloud-Agent-ID": "agent-code", "X-Cloud-Username": "bob"},
            409,
        ),
    ],
)
def test_registered_session_metadata_must_match(
    registry: Registry, headers: dict[str, str], expected_status: int
) -> None:
    bind_session(registry)
    harness = Harness(registry, ok_handler)

    async def scenario() -> httpx.Response:
        try:
            return await harness.request(
                "GET", "/session/ses_known/message", headers=headers
            )
        finally:
            await harness.close()

    response = run(scenario())
    assert response.status_code == expected_status
    assert len(harness.seen) == (1 if expected_status == 200 else 0)


def test_unknown_session_allows_complete_metadata_and_rejects_missing(
    registry: Registry,
) -> None:
    harness = Harness(registry, ok_handler)

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        try:
            allowed = await harness.request(
                "GET",
                "/session/ses_unknown/message",
                headers={
                    "X-Cloud-Agent-ID": "agent-code",
                    "X-Cloud-Username": "alice",
                },
            )
            rejected = await harness.request(
                "GET",
                "/session/ses_other/message",
                headers={"X-Cloud-Agent-ID": "agent-code"},
            )
            return allowed, rejected
        finally:
            await harness.close()

    allowed, rejected = run(scenario())
    assert allowed.status_code == 200
    assert rejected.status_code == 400
    assert harness.sandboxes.calls == [("agent-code", "alice")]


def test_session_status_is_not_treated_as_session_id(registry: Registry) -> None:
    bind_session(registry, session_id="ses_status-owner", username="bob")
    harness = Harness(registry, ok_handler)

    async def scenario() -> httpx.Response:
        try:
            return await harness.request(
                "GET",
                "/session/status",
                headers={
                    "X-Cloud-Agent-ID": "agent-code",
                    "X-Cloud-Username": "alice",
                },
            )
        finally:
            await harness.close()

    assert run(scenario()).status_code == 200
    assert harness.sandboxes.calls == [("agent-code", "alice")]


def test_unknown_native_path_is_forwarded_and_duplicate_query_is_preserved(
    registry: Registry,
) -> None:
    harness = Harness(registry, ok_handler)

    async def scenario() -> httpx.Response:
        try:
            return await harness.request(
                "GET",
                "/new/upstream/path?a=1&a=2&empty=",
                headers={
                    "X-Cloud-Agent-ID": "agent-code",
                    "X-Cloud-Username": "alice",
                },
            )
        finally:
            await harness.close()

    assert run(scenario()).status_code == 200
    assert harness.seen[0].url.path == "/new/upstream/path"
    assert harness.seen[0].url.query == b"a=1&a=2&empty="


def test_non_json_bytes_are_forwarded_unchanged(registry: Registry) -> None:
    harness = Harness(registry, ok_handler)
    raw = b"\x00\xffnative\r\nbytes"

    async def scenario() -> httpx.Response:
        try:
            return await harness.request(
                "POST",
                "/session/ses_unknown/shell",
                content=raw,
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-Cloud-Agent-ID": "agent-code",
                    "X-Cloud-Username": "alice",
                },
            )
        finally:
            await harness.close()

    assert run(scenario()).status_code == 200
    assert harness.seen[0].content == raw


def test_upstream_status_body_and_relevant_headers_are_transparent(
    registry: Registry,
) -> None:
    body = b'{"native":"failure"}'

    def upstream(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            418,
            content=body,
            headers={
                "Content-Type": "application/problem+json",
                "ETag": '"native-etag"',
                "X-Upstream": "yes",
                "Connection": "close",
                "Content-Length": str(len(body)),
            },
        )

    harness = Harness(registry, upstream)

    async def scenario() -> httpx.Response:
        try:
            return await harness.request(
                "GET",
                "/config",
                headers={
                    "X-Cloud-Agent-ID": "agent-code",
                    "X-Cloud-Username": "alice",
                },
            )
        finally:
            await harness.close()

    response = run(scenario())
    assert (response.status_code, response.content) == (418, body)
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["etag"] == '"native-etag"'
    assert response.headers["x-upstream"] == "yes"
    assert "connection" not in response.headers


def test_sandbox_error_becomes_503_without_upstream_call(registry: Registry) -> None:
    harness = Harness(registry, ok_handler, sandbox_error="runtime unavailable")

    async def scenario() -> httpx.Response:
        try:
            return await harness.request(
                "GET",
                "/config",
                headers={
                    "X-Cloud-Agent-ID": "agent-code",
                    "X-Cloud-Username": "alice",
                },
            )
        finally:
            await harness.close()

    response = run(scenario())
    assert response.status_code == 503
    assert response.json()["detail"] == "runtime unavailable"
    assert harness.seen == []


@pytest.mark.parametrize(
    ("path", "status"),
    [("/cloud/files/upload", 404), ("/cloud/health", 200), ("/doc", 200)],
)
def test_cloud_and_doc_paths_are_not_forwarded(
    registry: Registry, path: str, status: int
) -> None:
    harness = Harness(registry, ok_handler)

    async def scenario() -> httpx.Response:
        try:
            return await harness.request(
                "GET",
                path,
                headers={
                    "X-Cloud-Agent-ID": "agent-code",
                    "X-Cloud-Username": "alice",
                },
            )
        finally:
            await harness.close()

    assert run(scenario()).status_code == status
    assert harness.sandboxes.calls == []
    assert harness.seen == []
