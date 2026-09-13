"""Public API composition. Streams bytes; owns no catalog or routing database."""

from __future__ import annotations

import asyncio
import os
import re
import secrets
from contextlib import asynccontextmanager

import anyio
import httpx
from fastapi import FastAPI, HTTPException, Request
from starlette.responses import StreamingResponse

from api_gateway.api_docs import create_docs_router
from shared_libs.logging import RequestLogMiddleware, configure_logging, TRACE_CONTEXT
from shared_libs.service import ServiceAuthMiddleware, settings, run

HOP = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "upgrade",
    "proxy-authorization",
    "proxy-authenticate",
    "te",
    "trailer",
}


async def _await_cancellation_safe(task: asyncio.Task[None]) -> None:
    """Finish cleanup before preserving cancellation of its caller."""
    cancelled = False
    while not task.done():
        try:
            with anyio.CancelScope(shield=True):
                await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    try:
        await task
    except BaseException as exc:
        if cancelled:
            raise asyncio.CancelledError from exc
        raise
    if cancelled:
        raise asyncio.CancelledError


class _ClosingStreamingResponse(StreamingResponse):
    """Close one streamed upstream exactly once, including downstream cancellation."""

    def __init__(self, upstream: httpx.Response, **kwargs):
        self.upstream = upstream
        self._cleanup_task: asyncio.Task[None] | None = None
        super().__init__(self._chunks(), **kwargs)

    async def _perform_cleanup(self) -> None:
        with anyio.CancelScope(shield=True):
            await self.upstream.aclose()

    async def _cleanup(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._perform_cleanup())
        await _await_cancellation_safe(self._cleanup_task)

    async def _chunks(self):
        try:
            async for chunk in self.upstream.aiter_raw():
                yield chunk
        finally:
            await self._cleanup()

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._cleanup()


def destination(path: str):
    if path.startswith(("cloud/logs", "cloud/traces")):
        return "observability", "/" + path
    if path.startswith("llm/v1/"):
        return "model_gateway", "/" + path[len("llm/") :]
    if path.startswith("cloud/files/"):
        return "file_service", "/" + path
    if path.startswith(
        (
            "cloud/operations",
            "cloud/load-tests",
            "cloud/admin/load-tests",
            "cloud/admin/jobs",
            "cloud/admin/sandboxes",
            "cloud/admin/recovery",
        )
    ):
        return "operations", "/" + path
    if path == "cloud/admin/models/apply" or re.fullmatch(
        r"cloud/admin/agents/[^/]+/(apply|rollback|archive|restore|delete|delete-empty|delete-preview)",
        path,
    ):
        return "operations", "/" + path
    if path.startswith(
        (
            "cloud/admin",
            "cloud/agents",
            "cloud/providers",
            "cloud/models",
            "cloud/capabilities",
        )
    ):
        return "catalog_service", "/" + path
    return "sandbox_manager", "/" + path


def create_app(config=None, client=None):
    config = config or settings("api_gateway")
    owned = client is None
    client = client or httpx.AsyncClient(
        trust_env=False, timeout=httpx.Timeout(120, connect=10)
    )

    @asynccontextmanager
    async def lifespan(app):
        yield
        if owned:
            await client.aclose()

    application = FastAPI(
        title="OpenCode public API", version="1.0.0", lifespan=lifespan
    )
    configure_logging(
        module="api_gateway",
        log_root=config["log_root"],
        **config.get("settings", {}).get("logging", {}),
    )
    token = os.environ.get(
        "ADMIN_TOKEN", config.get("settings", {}).get("admin_token", "")
    )
    if token.startswith("${"):
        token = os.environ.get(token[2:-1], "")
    application.add_middleware(
        ServiceAuthMiddleware,
        token=token,
        public_paths=("/health/live", "/cloud/health"),
    )
    application.add_middleware(RequestLogMiddleware)
    from shared_libs.metrics import PlatformMetrics, MetricsMiddleware
    from starlette.responses import Response

    metrics = PlatformMetrics()
    application.add_middleware(MetricsMiddleware, metrics=metrics)
    application.add_api_route(
        "/metrics", lambda: Response(metrics.render(), media_type="text/plain")
    )
    application.include_router(create_docs_router())

    @application.get("/health/live")
    @application.get("/cloud/health")
    async def live():
        return {"ok": True}

    @application.get("/cloud/health/ready")
    async def ready():
        import asyncio

        async def check(module, url):
            try:
                response = await client.get(
                    url + "/health/ready",
                    headers={"Authorization": "Bearer " + config["service_token"]},
                    timeout=3,
                )
                return module, response.status_code == 200
            except httpx.HTTPError:
                return module, False

        state = dict(
            await asyncio.gather(
                *(
                    check(k, v)
                    for k, v in config["services"].items()
                    if k not in {"api_gateway", "observability"}
                )
            )
        )
        from starlette.responses import JSONResponse

        return JSONResponse(
            {"ok": all(state.values()), "modules": state},
            status_code=200 if all(state.values()) else 503,
        )

    @application.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def proxy(path: str, request: Request):
        if path.startswith("internal/") or path.startswith("health/"):
            raise HTTPException(404, "Not a public API")
        module, upstream_path = destination(path)
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in HOP | {"authorization"}
        }
        headers["Authorization"] = "Bearer " + config["service_token"]
        context = TRACE_CONTEXT.get()
        if context:
            headers["traceparent"] = f"00-{context['trace_id']}-{context['span_id']}-01"
        headers["X-Cloud-Request-ID"] = request.scope["cloud_log"]["request_id"]
        url = config["services"][module] + upstream_path
        if request.url.query:
            url += "?" + request.url.query
        upstream_request = client.build_request(
            request.method, url, headers=headers, content=request.stream()
        )
        if path in {"event", "global/event", "api/event"} or path.endswith("/event"):
            upstream_request.extensions["timeout"] = httpx.Timeout(
                None, connect=10
            ).as_dict()
        try:
            response = await client.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"{module} unavailable") from exc

        return _ClosingStreamingResponse(
            response,
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items() if k.lower() not in HOP},
        )

    return application


app = create_app()

if __name__ == "__main__":
    run("api_gateway")
