from __future__ import annotations

import asyncio
import tracemalloc
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import anyio
import pytest
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from fastapi import HTTPException

from app.gateway import SSEConnectionTracker, create_gateway_router
from app.registry import Registry
from app.sandbox import SandboxEndpoint


class ControlledStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes], *, pause_after_first: bool = False) -> None:
        self.chunks = chunks
        self.pause_after_first = pause_after_first
        self.first_yielded = asyncio.Event()
        self.continue_event = asyncio.Event()
        self.finished = asyncio.Event()
        self.closed = False

    async def __aiter__(self):
        try:
            for index, chunk in enumerate(self.chunks):
                yield chunk
                if index == 0:
                    self.first_yielded.set()
                    if self.pause_after_first:
                        await self.continue_event.wait()
        finally:
            self.finished.set()

    async def aclose(self) -> None:
        await anyio.sleep(0)
        self.closed = True


class GeneratedStream(httpx.AsyncByteStream):
    def __init__(self, count: int, chunk: bytes) -> None:
        self.count = count
        self.chunk = chunk
        self.closed = False

    async def __aiter__(self):
        for _ in range(self.count):
            yield self.chunk

    async def aclose(self) -> None:
        self.closed = True


class FakeUpstreamClient:
    def __init__(
        self,
        stream: httpx.AsyncByteStream,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.byte_stream = stream
        self.status = status
        self.headers = headers or {"Content-Type": "text/event-stream; charset=utf-8"}
        self.requests: list[httpx.Request] = []

    def build_request(
        self, method: str, url: str, *, headers: dict[str, str]
    ) -> httpx.Request:
        return httpx.Request(method, url, headers=headers)

    async def send(
        self, request: httpx.Request, *, stream: bool
    ) -> httpx.Response:
        assert stream is True
        self.requests.append(request)
        return httpx.Response(
            self.status,
            headers=self.headers,
            stream=self.byte_stream,
            request=request,
        )

    @asynccontextmanager
    async def stream(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        content: bytes,
    ):
        request = httpx.Request(method, url, headers=headers, content=content)
        self.requests.append(request)
        response = httpx.Response(
            self.status,
            headers=self.headers,
            stream=self.byte_stream,
            request=request,
        )
        try:
            yield response
        finally:
            await response.aclose()


class FakeSandboxes:
    def __init__(self) -> None:
        self.acquire_calls: list[tuple[str, str]] = []
        self.release_calls: list[SandboxEndpoint] = []

    async def acquire(self, agent_id: str, username: str) -> SandboxEndpoint:
        self.acquire_calls.append((agent_id, username))
        port = 41001 if username == "alice" else 41002
        return SandboxEndpoint(
            f"sbx-{agent_id}-{username}",
            f"container-{agent_id}-{username}",
            port,
            f"http://127.0.0.1:{port}",
            False,
        )

    async def release(self, endpoint: SandboxEndpoint, *, activity_persisted=False) -> None:
        await anyio.sleep(0)
        self.release_calls.append(endpoint)


def test_sse_connect_failure_releases_acquired_sandbox(registry: Registry):
    class FailingClient(FakeUpstreamClient):
        async def send(self, request, *, stream):
            raise httpx.ConnectError("injected connection failure")
    sandboxes = FakeSandboxes()
    tracker = SSEConnectionTracker()
    proxy = endpoint_for(registry, sandboxes, FailingClient(ControlledStream([])), tracker)
    with pytest.raises(HTTPException) as failure:
        asyncio.run(proxy(request("/event"), "event"))
    assert failure.value.status_code == 502
    assert len(sandboxes.release_calls) == 1
    assert tracker.active == 0


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    value = Registry(tmp_path / "sse.db")
    value.initialize()
    return value


def request(path: str, *, username: str = "alice") -> Request:
    headers = [
        (b"x-cloud-agent-id", b"agent-code"),
        (b"x-cloud-username", username.encode()),
        (b"accept", b"text/event-stream"),
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("gateway.test", 80),
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def endpoint_for(
    registry: Registry,
    sandboxes: FakeSandboxes,
    upstream: FakeUpstreamClient,
    tracker: SSEConnectionTracker,
):
    router = create_gateway_router(registry, sandboxes, upstream, tracker)  # type: ignore[arg-type]
    return router.routes[0].endpoint


def run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


@pytest.mark.parametrize(
    ("path", "upstream_path"), [("/event", "/event"), ("/global/event", "/global/event"),
                              ("/api/event", "/api/event"),
                              ("/api/session/ses_known/event", "/api/session/ses_known/event")]
)
def test_event_routes_preserve_content_type_chunk_order_and_bytes(
    registry: Registry, path: str, upstream_path: str
) -> None:
    chunks = [b"event: one\ndata: \xff\n\n", b": heartbeat\n\n", b"data: three\n\n"]
    stream = ControlledStream(chunks)
    upstream = FakeUpstreamClient(
        stream, headers={"Content-Type": "text/event-stream; charset=latin-1"}
    )
    sandboxes = FakeSandboxes()
    tracker = SSEConnectionTracker()
    proxy = endpoint_for(registry, sandboxes, upstream, tracker)

    async def scenario() -> tuple[StreamingResponse, list[bytes]]:
        response = await proxy(request(path), path.lstrip("/"))
        assert isinstance(response, StreamingResponse)
        received = [chunk async for chunk in response.body_iterator]
        return response, received

    response, received = run(scenario())
    assert response.headers["content-type"] == "text/event-stream; charset=latin-1"
    assert received == chunks
    assert upstream.requests[0].url.path == upstream_path
    assert stream.closed is True
    assert len(sandboxes.release_calls) == 1
    assert tracker.active == 0


def test_first_chunk_is_observable_before_upstream_finishes(
    registry: Registry,
) -> None:
    stream = ControlledStream([b"data: first\n\n", b"data: second\n\n"], pause_after_first=True)
    upstream = FakeUpstreamClient(stream)
    sandboxes = FakeSandboxes()
    tracker = SSEConnectionTracker()
    proxy = endpoint_for(registry, sandboxes, upstream, tracker)

    async def scenario() -> None:
        response = await proxy(request("/event"), "event")
        assert isinstance(response, StreamingResponse)
        iterator = response.body_iterator.__aiter__()
        first = await iterator.__anext__()
        assert first == b"data: first\n\n"
        assert stream.finished.is_set() is False
        assert tracker.active == 1
        stream.continue_event.set()
        assert await iterator.__anext__() == b"data: second\n\n"
        with pytest.raises(StopAsyncIteration):
            await iterator.__anext__()

    run(scenario())
    assert stream.closed is True
    assert tracker.active == 0
    assert len(sandboxes.release_calls) == 1


def test_cancel_close_releases_upstream_sandbox_and_gauge(
    registry: Registry,
) -> None:
    stream = ControlledStream([b"data: first\n\n", b"data: never\n\n"], pause_after_first=True)
    upstream = FakeUpstreamClient(stream)
    sandboxes = FakeSandboxes()
    tracker = SSEConnectionTracker()
    proxy = endpoint_for(registry, sandboxes, upstream, tracker)

    async def scenario() -> None:
        response = await proxy(request("/event"), "event")
        iterator = response.body_iterator.__aiter__()
        assert await iterator.__anext__() == b"data: first\n\n"
        assert tracker.active == 1
        pending = asyncio.create_task(iterator.__anext__())
        await asyncio.sleep(0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

    run(scenario())
    assert stream.closed is True
    assert len(sandboxes.release_calls) == 1
    assert tracker.active == 0


def test_disconnect_before_upstream_headers_cancels_request_and_releases(registry: Registry):
    async def scenario():
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class SilentClient(FakeUpstreamClient):
            async def send(self, request, *, stream):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        first = True
        async def receive():
            nonlocal first
            if first:
                first = False
                return {"type": "http.request", "body": b"", "more_body": False}
            await started.wait()
            return {"type": "http.disconnect"}

        sandboxes = FakeSandboxes()
        tracker = SSEConnectionTracker()
        proxy = endpoint_for(registry, sandboxes, SilentClient(ControlledStream([])), tracker)
        downstream = Request(request("/event").scope, receive)
        with pytest.raises(HTTPException) as failure:
            await asyncio.wait_for(proxy(downstream, "event"), 2)
        assert failure.value.status_code == 499
        assert cancelled.is_set()
        assert len(sandboxes.release_calls) == 1
        assert tracker.active == 0

    asyncio.run(scenario())


def test_sse_upstream_send_cancellation_releases_inside_anyio_cancel_scope(
    registry: Registry,
) -> None:
    class BlockingClient(FakeUpstreamClient):
        def __init__(self) -> None:
            super().__init__(ControlledStream([]))
            self.started = anyio.Event()

        async def send(self, request, *, stream):
            self.started.set()
            await anyio.sleep_forever()

    upstream = BlockingClient()
    sandboxes = FakeSandboxes()
    tracker = SSEConnectionTracker()
    proxy = endpoint_for(registry, sandboxes, upstream, tracker)

    async def scenario() -> None:
        async def connect() -> None:
            await proxy(request("/event"), "event")

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(connect)
            await upstream.started.wait()
            tasks.cancel_scope.cancel()

    anyio.run(scenario)
    assert len(sandboxes.release_calls) == 1
    assert tracker.active == 0


def test_asgi_disconnect_completes_cleanup_inside_cancel_scope(registry: Registry) -> None:
    stream = ControlledStream([b"data: first\n\n", b"data: never\n\n"], pause_after_first=True)
    upstream = FakeUpstreamClient(stream)
    sandboxes = FakeSandboxes()
    tracker = SSEConnectionTracker()
    proxy = endpoint_for(registry, sandboxes, upstream, tracker)

    async def scenario() -> None:
        response = await proxy(request("/event"), "event")
        disconnected = False

        async def receive() -> dict[str, Any]:
            nonlocal disconnected
            if not disconnected:
                disconnected = True
                await stream.first_yielded.wait()
            return {"type": "http.disconnect"}

        async def send(_message: dict[str, Any]) -> None:
            await anyio.sleep(0)

        await response(request("/event").scope, receive, send)

    run(scenario())
    assert stream.closed is True
    assert len(sandboxes.release_calls) == 1
    assert tracker.active == 0


def test_asgi_first_send_cancellation_still_releases_once(registry: Registry) -> None:
    stream = ControlledStream([b"data: unused\n\n"])
    upstream = FakeUpstreamClient(stream)
    sandboxes = FakeSandboxes()
    tracker = SSEConnectionTracker()
    proxy = endpoint_for(registry, sandboxes, upstream, tracker)

    async def scenario() -> None:
        response = await proxy(request("/event"), "event")

        async def receive() -> dict[str, Any]:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        async def send(_message: dict[str, Any]) -> None:
            asyncio.current_task().cancel()
            await anyio.sleep(0)

        await response(request("/event").scope, receive, send)

    run(scenario())
    assert stream.closed is True
    assert len(sandboxes.release_calls) == 1
    assert tracker.active == 0


def test_aclose_failure_does_not_leak_or_double_cleanup(registry: Registry) -> None:
    class FailingCloseClient(FakeUpstreamClient):
        async def send(self, request, *, stream):
            response = await super().send(request, stream=stream)
            original_close = response.aclose

            async def failing_close() -> None:
                await original_close()
                await anyio.sleep(0)
                raise RuntimeError("injected close failure")

            response.aclose = failing_close
            return response

    stream = ControlledStream([b"data: one\n\n"])
    upstream = FailingCloseClient(stream)
    sandboxes = FakeSandboxes()
    tracker = SSEConnectionTracker()
    proxy = endpoint_for(registry, sandboxes, upstream, tracker)

    async def scenario() -> None:
        response = await proxy(request("/event"), "event")
        iterator = response.body_iterator.__aiter__()
        assert await iterator.__anext__() == b"data: one\n\n"
        with pytest.raises(RuntimeError, match="injected close failure"):
            await iterator.__anext__()
        # A second cleanup call awaits the same task and cannot close/release twice.
        with pytest.raises(RuntimeError, match="injected close failure"):
            await response._cleanup()

    run(scenario())
    assert stream.closed is True
    assert len(sandboxes.release_calls) == 1
    assert tracker.active == 0


def test_alice_and_bob_acquire_and_release_their_own_endpoints(
    registry: Registry,
) -> None:
    sandboxes = FakeSandboxes()
    tracker = SSEConnectionTracker()

    async def one(username: str) -> tuple[str, bytes]:
        stream = ControlledStream([f"data: {username}\n\n".encode()])
        upstream = FakeUpstreamClient(stream)
        proxy = endpoint_for(registry, sandboxes, upstream, tracker)
        response = await proxy(request("/event", username=username), "event")
        body = b"".join([chunk async for chunk in response.body_iterator])
        return upstream.requests[0].url.host or "", body

    async def scenario() -> list[tuple[str, bytes]]:
        return await asyncio.gather(one("alice"), one("bob"))

    results = run(scenario())
    assert sandboxes.acquire_calls == [
        ("agent-code", "alice"),
        ("agent-code", "bob"),
    ]
    assert results == [
        ("127.0.0.1", b"data: alice\n\n"),
        ("127.0.0.1", b"data: bob\n\n"),
    ]
    assert [item.host_port for item in sandboxes.release_calls] == [41001, 41002]
    assert tracker.active == 0


def test_normal_path_still_buffers_before_returning_response(
    registry: Registry,
) -> None:
    stream = ControlledStream([b"first-", b"second"], pause_after_first=True)
    upstream = FakeUpstreamClient(
        stream, headers={"Content-Type": "application/octet-stream"}
    )
    sandboxes = FakeSandboxes()
    tracker = SSEConnectionTracker()
    proxy = endpoint_for(registry, sandboxes, upstream, tracker)

    async def scenario() -> Response:
        task = asyncio.create_task(proxy(request("/file"), "file"))
        await stream.first_yielded.wait()
        assert task.done() is False
        stream.continue_event.set()
        return await task

    response = run(scenario())
    assert isinstance(response, Response)
    assert not isinstance(response, StreamingResponse)
    assert response.body == b"first-second"
    assert stream.closed is True
    assert len(sandboxes.release_calls) == 1
    assert tracker.active == 0


def test_long_sse_stream_has_bounded_proxy_memory(registry: Registry) -> None:
    stream = GeneratedStream(20_000, b"data: " + b"x" * 1016 + b"\n\n")
    upstream = FakeUpstreamClient(stream)
    sandboxes = FakeSandboxes()
    tracker = SSEConnectionTracker()
    proxy = endpoint_for(registry, sandboxes, upstream, tracker)

    async def scenario() -> int:
        response = await proxy(request("/event"), "event")
        tracemalloc.start()
        try:
            async for _chunk in response.body_iterator:
                pass
            _current, peak = tracemalloc.get_traced_memory()
            return peak
        finally:
            tracemalloc.stop()

    peak = run(scenario())
    assert peak < 5 * 1024 * 1024
    assert stream.closed is True
    assert tracker.active == 0
