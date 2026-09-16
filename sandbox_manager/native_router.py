"""Transparent proxy for native OpenCode HTTP endpoints."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import anyio
import httpx
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import Response, StreamingResponse

from sandbox_manager.registry import Registry, SessionRoute
from shared_libs.metrics import PlatformMetrics
from sandbox_manager.backend import LocalDockerBackend, SandboxEndpoint, SandboxError
from shared_libs.logging import bind_request, emit, safe_request_id
from sandbox_manager.session_binding import (
    SessionBindings,
    flattened_events,
    directory_collection,
)


_SESSION_PATH = re.compile(r"^(?:api/)?session/(ses_[^/]+)(?:/|$)")
_SESSION_EVENT_PATH = re.compile(r"^api/session/[^/]+/event$")
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
_CLOUD_HEADERS = {
    "x-cloud-agent-id",
    "x-cloud-username",
    "x-cloud-request-id",
    "x-cloud-session-id",
}


@dataclass(frozen=True)
class RouteMetadata:
    agent_id: str | None = None
    username: str | None = None
    session_workspace: str | None = None
    request_id: str | None = None


class SSEConnectionTracker:
    """In-process active connection gauge, wired to Prometheus in task 20."""

    def __init__(self) -> None:
        self.active = 0

    def opened(self) -> None:
        self.active += 1

    def closed(self) -> None:
        self.active -= 1
        if self.active < 0:
            raise RuntimeError("SSE connection gauge underflow")


class _TrackedStreamingResponse(StreamingResponse):
    def __init__(self, *args, cleanup: Callable[[], Awaitable[None]], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cleanup = cleanup

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._cleanup()


async def _await_cancellation_safe(task: asyncio.Task[None]) -> None:
    """Finish a cleanup task, then preserve cancellation of its caller."""
    cancelled = False
    while not task.done():
        try:
            with anyio.CancelScope(shield=True):
                await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
            continue
    try:
        await task
    except BaseException as exc:
        if cancelled:
            raise asyncio.CancelledError from exc
        raise
    if cancelled:
        raise asyncio.CancelledError


class SessionRecorder:
    """Group concurrent route commits while awaiting durability for every caller."""

    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.pending: list[tuple[tuple, asyncio.Future]] = []
        self.worker: asyncio.Task | None = None

    async def record(self, *entry) -> SessionRoute:
        future = asyncio.get_running_loop().create_future()
        self.pending.append((entry, future))
        if self.worker is None or self.worker.done():
            self.worker = asyncio.create_task(self._flush())
        return await future

    async def _flush(self) -> None:
        while self.pending:
            # A bounded 5ms collection window avoids eight separate fsyncs
            # during a burst. No response returns before the shared commit.
            await asyncio.sleep(0.005)
            batch, self.pending = self.pending[:64], self.pending[64:]
            try:
                results = await asyncio.to_thread(
                    self.registry.record_sessions_batch, [entry for entry, _ in batch]
                )
            except Exception as exc:
                results = [exc] * len(batch)
            for (_, future), result in zip(batch, results):
                if future.done():
                    continue
                if isinstance(result, Exception):
                    future.set_exception(result)
                else:
                    future.set_result(result)


def create_gateway_router(
    registry: Registry,
    sandboxes: LocalDockerBackend,
    client: httpx.AsyncClient,
    sse_tracker: SSEConnectionTracker | None = None,
    metrics: PlatformMetrics | None = None,
) -> APIRouter:
    router = APIRouter(include_in_schema=False)
    tracker = sse_tracker or SSEConnectionTracker()
    session_recorder = SessionRecorder(registry)
    bindings = (
        SessionBindings(registry, sandboxes.workspaces, client)
        if hasattr(sandboxes, "workspaces")
        else None
    )

    @router.api_route(
        "/{native_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def proxy(request: Request, native_path: str) -> Response:
        if native_path == "doc" or native_path.startswith("cloud/"):
            raise HTTPException(status_code=404, detail="route not found")
        if bindings and native_path in {
            "experimental/control-plane/move-session",
            "experimental/workspace/warp",
        }:
            raise HTTPException(403, "Session directories are managed by the platform")

        body = await request.body()
        metadata, upstream_body = _extract_metadata(request, body)
        metadata = RouteMetadata(
            metadata.agent_id,
            metadata.username,
            metadata.session_workspace,
            safe_request_id(
                metadata.request_id
                or request.scope.get("cloud_log", {}).get("request_id")
            ),
        )
        lookup_started = time.perf_counter()
        route = _session_route(registry, native_path)
        context_session = request.headers.get("x-cloud-session-id")
        if bindings and context_session:
            contextual = registry.get_session_route(context_session)
            if contextual is None:
                raise HTTPException(404, "Unknown session context")
            if route and route.session_id != context_session:
                raise HTTPException(409, "Session context conflicts with URL")
            route = route or contextual
        agent_id, username = _resolve_owner(route, metadata)
        management = getattr(sandboxes, "management", None)
        management_lease = False
        if management:
            try:
                payload = json.loads(upstream_body) if upstream_body else {}
            except ValueError:
                raise HTTPException(400, "Invalid JSON")
            management_lease = await asyncio.to_thread(
                management.authorize, agent_id, request.method, native_path, payload
            )
            if upstream_body and isinstance(payload, dict):
                upstream_body = json.dumps(payload).encode()
            if management_lease:
                management.lease(agent_id, True)
        bind_request(
            request.scope,
            request_id=metadata.request_id,
            component="gateway",
            agent_id=agent_id,
            username=username,
            session_id=route.session_id if route else None,
        )
        if upstream_body and request.headers.get("content-type", "").startswith(
            "application/json"
        ):
            try:
                native_payload = json.loads(upstream_body)
                if isinstance(native_payload, dict):
                    model = native_payload.get("model")
                    bind_request(
                        request.scope,
                        message_id=native_payload.get("messageID"),
                        logical_model=model.get("modelID")
                        if isinstance(model, dict)
                        else None,
                    )
            except (ValueError, TypeError):
                pass
        if metrics is not None:
            metrics.route_lookup.observe(time.perf_counter() - lookup_started)
        if management:
            management.acquiring[agent_id] = management.acquiring.get(agent_id, 0) + 1
        try:
            endpoint = await sandboxes.acquire(agent_id, username)
        except SandboxError as exc:
            if management_lease:
                management.lease(agent_id, False)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except BaseException:
            if management_lease:
                management.lease(agent_id, False)
            raise
        finally:
            if management:
                management.acquiring[agent_id] -= 1
        context = bind_request(
            request.scope,
            sandbox_id=endpoint.sandbox_id,
            container_id=endpoint.container_id,
        )
        emit("sandbox_acquired", **{**context, "component": "sandbox"})

        url = f"{endpoint.base_url}/{native_path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"
        headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower()
            not in _HOP_BY_HOP
            | _CLOUD_HEADERS
            | {"host", "content-length"}
            | ({"authorization"} if management else set())
        }
        headers["X-Cloud-Request-ID"] = metadata.request_id
        if (
            bindings
            and request.method == "POST"
            and native_path.rstrip("/") in {"session", "api/session"}
        ):
            url = str(
                httpx.URL(url)
                .copy_remove_param("workspace")
                .copy_set_param("directory", "/workspace")
            )
            headers.pop("x-opencode-directory", None)
            headers.pop("x-opencode-workspace", None)
        flatten = bool(bindings and native_path == "event")
        if flatten:
            url = endpoint.base_url + "/global/event"
        if bindings and request.method == "GET" and native_path == "session":
            # Native /session is directory-filtered. The sandbox is already
            # isolated by Agent x User, so use its cross-directory session list.
            url = str(
                httpx.URL(
                    endpoint.base_url + "/experimental/session"
                ).copy_merge_params(
                    [
                        (k, v)
                        for k, v in request.query_params.multi_items()
                        if k not in {"directory", "workspace", "path", "scope"}
                    ]
                )
            )
        if request.method == "GET" and (
            native_path in {"event", "global/event", "api/event"}
            or _SESSION_EVENT_PATH.fullmatch(native_path)
        ):
            return await _stream_sse(
                client,
                sandboxes,
                endpoint,
                url,
                headers,
                tracker,
                request,
                flatten=flatten,
            )
        activity_persisted = False
        try:
            if (
                bindings
                and not route
                and request.method == "GET"
                and native_path in {"session/status", "permission", "question"}
            ):
                try:
                    collection = await directory_collection(
                        client, registry, endpoint, "/" + native_path
                    )
                except (httpx.HTTPError, ValueError) as exc:
                    raise HTTPException(
                        502, "Could not read state across session directories"
                    ) from exc
                return Response(
                    content=json.dumps(collection), media_type="application/json"
                )
            if (
                bindings
                and route
                and request.method not in {"GET", "HEAD", "DELETE"}
                and not native_path.endswith(("/abort", "/interrupt"))
            ):
                await bindings.ensure(endpoint, route)
            if bindings and route:
                url = str(
                    httpx.URL(url)
                    .copy_remove_param("workspace")
                    .copy_set_param(
                        "directory", f"/workspace/sessions/{route.session_id}"
                    )
                )
                headers.pop("x-opencode-directory", None)
                headers.pop("x-opencode-workspace", None)
            try:
                async with client.stream(
                    request.method, url, headers=headers, content=upstream_body
                ) as upstream:
                    content = b"".join([chunk async for chunk in upstream.aiter_raw()])
                    response_headers = {
                        name: value
                        for name, value in upstream.headers.items()
                        if name.lower() not in _HOP_BY_HOP | {"content-length"}
                    }
                    status = upstream.status_code
            except httpx.HTTPError as exc:
                raise HTTPException(
                    status_code=502, detail=f"OpenCode upstream failed: {exc}"
                ) from exc

            if (
                request.method == "POST"
                and (
                    native_path.rstrip("/") in {"session", "api/session"}
                    or (bindings and route and native_path.endswith("/fork"))
                )
                and 200 <= status < 300
            ):
                created_session_id = await _record_created_session(
                    registry,
                    endpoint,
                    agent_id,
                    username,
                    metadata,
                    content,
                    session_recorder,
                    v2=native_path.rstrip("/") == "api/session",
                )
                activity_persisted = True
                bind_request(request.scope, session_id=created_session_id)
                if bindings:
                    bound = await bindings.ensure(
                        endpoint, registry.get_session_route(created_session_id)
                    )
                    payload = json.loads(content)
                    if native_path.rstrip("/") == "api/session":
                        payload["data"].update(directory=bound["directory"])
                    else:
                        payload.update(directory=bound["directory"])
                    content = json.dumps(payload).encode()
                    response_headers.pop("content-encoding", None)
            elif (
                request.method == "POST"
                and native_path.endswith("/message")
                and 200 <= status < 300
            ):
                try:
                    info = json.loads(content).get("info", {})
                    bind_request(request.scope, message_id=info.get("parentID"))
                except (ValueError, TypeError, AttributeError):
                    pass
            if (
                management
                and request.method == "GET"
                and native_path in {"config", "global/config"}
            ):
                from shared_libs.validation import redact

                try:
                    content = json.dumps(redact(json.loads(content))).encode()
                    response_headers.pop("content-encoding", None)
                except (ValueError, TypeError):
                    raise HTTPException(
                        502, "Could not read managed runtime configuration"
                    )
            return Response(
                content=content, status_code=status, headers=response_headers
            )
        finally:
            if management_lease:
                management.lease(agent_id, False)
            if activity_persisted:
                await sandboxes.release(endpoint, activity_persisted=True)
            else:
                await sandboxes.release(endpoint)

    return router


async def _stream_sse(
    client: httpx.AsyncClient,
    sandboxes: LocalDockerBackend,
    endpoint: SandboxEndpoint,
    url: str,
    headers: dict[str, str],
    tracker: SSEConnectionTracker,
    downstream: Request,
    *,
    flatten: bool = False,
) -> StreamingResponse:
    request = client.build_request("GET", url, headers=headers)
    request.extensions["timeout"] = httpx.Timeout(None).as_dict()

    async def wait_disconnect() -> None:
        while not await downstream.is_disconnected():
            await asyncio.sleep(0.05)

    pending = asyncio.create_task(client.send(request, stream=True))
    disconnected = asyncio.create_task(wait_disconnect())
    try:
        done, _ = await asyncio.wait(
            {pending, disconnected}, return_when=asyncio.FIRST_COMPLETED
        )
        if disconnected in done:
            raise HTTPException(
                status_code=499,
                detail="SSE client disconnected before upstream headers",
            )
        upstream = pending.result()
    except BaseException as exc:

        async def cancel_pending() -> None:
            pending.cancel()
            try:
                response = await pending
            except BaseException:
                pass
            else:
                await response.aclose()

        try:
            await _await_cancellation_safe(asyncio.create_task(cancel_pending()))
        finally:
            release_task = asyncio.create_task(sandboxes.release(endpoint))
            await _await_cancellation_safe(release_task)
        if isinstance(exc, httpx.HTTPError):
            raise HTTPException(
                status_code=502, detail=f"OpenCode upstream failed: {exc}"
            ) from exc
        raise
    finally:
        disconnected.cancel()
        try:
            await disconnected
        except asyncio.CancelledError:
            pass

    response_headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() not in _HOP_BY_HOP | {"content-length"}
    }
    if flatten:
        response_headers.pop("content-encoding", None)

    cleanup_task: asyncio.Task[None] | None = None
    observers = getattr(sandboxes, "event_subscribers", None)
    if observers is None:
        observers = sandboxes.event_subscribers = {}
    observers[endpoint.sandbox_id] = observers.get(endpoint.sandbox_id, 0) + 1

    async def perform_cleanup() -> None:
        error: BaseException | None = None
        with anyio.CancelScope(shield=True):
            try:
                await upstream.aclose()
            except BaseException as exc:
                error = exc
            finally:
                try:
                    tracker.closed()
                except BaseException as exc:
                    if error is None:
                        error = exc
                finally:
                    remaining = observers.get(endpoint.sandbox_id, 0) - 1
                    if remaining > 0:
                        observers[endpoint.sandbox_id] = remaining
                    else:
                        observers.pop(endpoint.sandbox_id, None)
                    try:
                        await sandboxes.release(endpoint)
                    except BaseException as exc:
                        if error is None:
                            error = exc
        if error is not None:
            raise error

    async def cleanup() -> None:
        nonlocal cleanup_task
        if cleanup_task is None:
            cleanup_task = asyncio.create_task(perform_cleanup())
        await _await_cancellation_safe(cleanup_task)

    async def chunks():
        try:
            async for chunk in (
                flattened_events(upstream) if flatten else upstream.aiter_raw()
            ):
                yield chunk
        finally:
            await cleanup()

    tracker.opened()
    return _TrackedStreamingResponse(
        chunks(),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=None,
        cleanup=cleanup,
    )


def _extract_metadata(request: Request, body: bytes) -> tuple[RouteMetadata, bytes]:
    header_metadata = RouteMetadata(
        agent_id=request.headers.get("x-cloud-agent-id"),
        username=request.headers.get("x-cloud-username"),
        request_id=request.headers.get("x-cloud-request-id"),
    )
    content_type = (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    )
    if (
        request.method not in {"POST", "PUT", "PATCH"}
        or content_type != "application/json"
        or not body
    ):
        return header_metadata, body
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="invalid JSON request body"
        ) from exc
    if not isinstance(payload, dict):
        return header_metadata, body
    cloud = payload.pop("_cloud", None)
    if cloud is None:
        return header_metadata, body
    if not isinstance(cloud, dict):
        raise HTTPException(status_code=400, detail="_cloud must be an object")
    metadata = RouteMetadata(
        agent_id=_optional_string(cloud, "agent_id"),
        username=_optional_string(cloud, "username"),
        session_workspace=_optional_string(cloud, "session_workspace"),
        request_id=_optional_string(cloud, "request_id") or header_metadata.request_id,
    )
    if (
        header_metadata.request_id
        and metadata.request_id
        and header_metadata.request_id != metadata.request_id
    ):
        raise HTTPException(status_code=409, detail="conflicting request IDs")
    if (
        header_metadata.agent_id
        and metadata.agent_id
        and header_metadata.agent_id != metadata.agent_id
    ):
        raise HTTPException(
            status_code=409, detail="conflicting Agent routing metadata"
        )
    if (
        header_metadata.username
        and metadata.username
        and header_metadata.username != metadata.username
    ):
        raise HTTPException(status_code=409, detail="conflicting user routing metadata")
    metadata = RouteMetadata(
        metadata.agent_id or header_metadata.agent_id,
        metadata.username or header_metadata.username,
        metadata.session_workspace,
        metadata.request_id,
    )
    return metadata, json.dumps(payload, separators=(",", ":")).encode()


def _optional_string(mapping: dict[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    if value is not None and (not isinstance(value, str) or not value):
        raise HTTPException(
            status_code=400, detail=f"_cloud.{key} must be a non-empty string"
        )
    return value


def _session_route(registry: Registry, native_path: str) -> SessionRoute | None:
    match = _SESSION_PATH.match(native_path)
    return registry.get_session_route(match.group(1)) if match else None


def _resolve_owner(
    route: SessionRoute | None, metadata: RouteMetadata
) -> tuple[str, str]:
    if route is not None:
        if metadata.agent_id and metadata.agent_id != route.agent_id:
            raise HTTPException(
                status_code=409, detail="session Agent route conflicts with request"
            )
        if metadata.username and metadata.username != route.username:
            raise HTTPException(
                status_code=409, detail="session user route conflicts with request"
            )
        return route.agent_id, route.username
    if not metadata.agent_id or not metadata.username:
        raise HTTPException(
            status_code=400, detail="Agent and username routing metadata are required"
        )
    return metadata.agent_id, metadata.username


async def _record_created_session(
    registry: Registry,
    endpoint: SandboxEndpoint,
    agent_id: str,
    username: str,
    metadata: RouteMetadata,
    content: bytes,
    recorder: SessionRecorder,
    *,
    v2: bool = False,
) -> str:
    try:
        payload = json.loads(content)
        if v2:
            payload = payload["data"]
        session_id = payload["id"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=502, detail="OpenCode session response lacks an ID"
        ) from exc
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(
            status_code=502, detail="OpenCode session response has an invalid ID"
        )
    workspace = metadata.session_workspace or f"sessions/{session_id}"
    try:
        await recorder.record(
            session_id,
            endpoint.sandbox_id,
            agent_id,
            username,
            workspace,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return session_id
