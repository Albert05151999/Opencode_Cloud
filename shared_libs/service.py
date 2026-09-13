"""Small service bootstrap contract; no imports of business services."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

import httpx
from fastapi import FastAPI
from starlette.responses import JSONResponse

from shared_libs.logging import RequestLogMiddleware, configure_logging, TRACE_CONTEXT


def settings(module: str) -> dict:
    path = os.environ.get("MODULE_CONFIG")
    result = json.loads(Path(path).read_text()) if path else {}
    if result.get("module_id", module) != module:
        raise ValueError("Configuration module_id does not match service")
    result.setdefault("module_id", module)
    result["data_root"] = os.environ.get(
        "DATA_ROOT", result.get("data_root", f"data/{module}")
    )
    result["log_root"] = os.environ.get("LOG_ROOT", result.get("log_root", "log"))
    result["port"] = int(os.environ.get("SERVICE_PORT", result.get("port", 8080)))
    result["host"] = os.environ.get("SERVICE_HOST", result.get("host", "0.0.0.0"))
    result.setdefault("settings", {})
    result.setdefault("services", {})
    for key in (
        "api_gateway",
        "catalog_service",
        "sandbox_manager",
        "file_service",
        "operations",
        "observability",
        "model_gateway",
    ):
        result["services"][key] = os.environ.get(
            key.upper() + "_URL", result["services"].get(key, f"http://{key}:8080")
        )
    token = os.environ.get("SERVICE_TOKEN", result.get("service_token", ""))
    if isinstance(token, dict):
        token = os.environ.get(token.get("env", "SERVICE_TOKEN"), "")
    if isinstance(token, str) and token.startswith("${") and token.endswith("}"):
        token = os.environ.get(token[2:-1], "")
    result["service_token"] = token
    return result


class ServiceAuthMiddleware:
    def __init__(self, app, token: str, public_paths=("/health/live",)):
        self.app, self.token, self.public_paths = app, token, set(public_paths)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] not in self.public_paths:
            headers = dict(scope.get("headers", []))
            supplied = headers.get(b"authorization", b"").decode("latin1")
            if not self.token or not secrets.compare_digest(
                supplied, "Bearer " + self.token
            ):
                await JSONResponse(
                    {"detail": "Service credential required"}, status_code=401
                )(scope, receive, send)
                return
        await self.app(scope, receive, send)


def propagate_headers(request):
    context = TRACE_CONTEXT.get()
    if context.get("trace_id") and context.get("span_id"):
        request.headers["traceparent"] = (
            f"00-{context['trace_id']}-{context['span_id']}-01"
        )
    if context.get("request_id"):
        request.headers["X-Cloud-Request-ID"] = context["request_id"]
    if context.get("job_id"):
        request.headers["X-Cloud-Job-ID"] = context["job_id"]
    if context.get("session_id"):
        request.headers["X-Cloud-Session-ID"] = context["session_id"]
    if context.get("message_id"):
        request.headers["X-Cloud-Message-ID"] = context["message_id"]


def internal_sync_client(config: dict, module: str, **kwargs) -> httpx.Client:
    return httpx.Client(
        event_hooks={"request": [propagate_headers]},
        base_url=config["services"][module],
        headers={"Authorization": "Bearer " + config["service_token"]},
        trust_env=False,
        timeout=30,
        **kwargs,
    )


def internal_client(config: dict, module: str, **kwargs) -> httpx.AsyncClient:
    async def propagate(request):
        propagate_headers(request)

    return httpx.AsyncClient(
        event_hooks={"request": [propagate]},
        base_url=config["services"][module],
        headers={"Authorization": "Bearer " + config["service_token"]},
        trust_env=False,
        timeout=30,
        **kwargs,
    )


def configure_service(
    app: FastAPI, module: str, config: dict | None = None, *, metrics=None
) -> dict:
    config = config or settings(module)
    from shared_libs.metrics import PlatformMetrics, MetricsMiddleware
    from starlette.responses import Response

    metrics = metrics or PlatformMetrics()
    app.state.metrics = metrics
    app.add_middleware(MetricsMiddleware, metrics=metrics)
    app.add_api_route(
        "/metrics", lambda: Response(metrics.render(), media_type="text/plain")
    )
    app.state.config = config
    configure_logging(
        os.environ.get("LOG_LEVEL", "INFO"),
        module=module,
        log_root=config["log_root"],
        **config.get("settings", {}).get("logging", {}),
    )
    app.add_middleware(ServiceAuthMiddleware, token=config["service_token"])
    app.add_middleware(RequestLogMiddleware)

    @app.get("/health/live")
    async def live():
        return {"ok": True, "module": module}

    return config


def run(module: str):
    import uvicorn

    config = settings(module)
    uvicorn.run(f"{module}.main:app", host=config["host"], port=config["port"])
