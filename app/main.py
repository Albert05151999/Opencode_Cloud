"""Controller application entry point."""
from __future__ import annotations

import argparse
import asyncio
import json
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Iterable

import uvicorn
import httpx
from fastapi import APIRouter, FastAPI
from starlette.responses import Response

from app.config import AppConfig, load_config
from app.auth import create_auth_router
from app.api_docs import create_docs_router
from app.files import create_files_router
from app.gateway import create_gateway_router
from app.health import HealthMonitor, create_health_router
from app.metrics import MetricsMiddleware, PlatformMetrics
from app.registry import Registry
from app.sandbox import LocalDockerBackend
from app.workspace import WorkspaceManager
from app.observability import RequestLogMiddleware, configure_logging, emit


def create_app(
    gateway_router: APIRouter | None = None,
    *,
    cloud_routers: Iterable[APIRouter] = (),
    metrics: PlatformMetrics | None = None,
    lifespan=None,
    metrics_enabled: bool = True,
    metrics_path: str = "/metrics",
) -> FastAPI:
    application = FastAPI(title="OpenCode Cloud Controller", version="0.2.2", lifespan=lifespan)
    application.add_middleware(RequestLogMiddleware)
    metrics = metrics or PlatformMetrics()
    application.state.metrics = metrics
    async def prometheus_metrics() -> Response:
        return Response(metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")
    if metrics_enabled:
        application.add_middleware(MetricsMiddleware, metrics=metrics)
        application.add_api_route(metrics_path, prometheus_metrics, include_in_schema=False)

    @application.get("/cloud/health", tags=["cloud"])
    async def health() -> dict[str, bool]:
        return {"ok": True}

    for router in cloud_routers:
        application.include_router(router)
    application.include_router(create_docs_router())
    if gateway_router is not None:
        application.include_router(gateway_router)
    return application


app = create_app()


def build_app(config: AppConfig, agents_root: Path) -> FastAPI:
    """Compose the controller using one registry, client and metric registry."""
    if config.auth.enabled:
        raise RuntimeError("Authentication adapter is not implemented yet")
    registry = Registry(Path(config.platform.data_root) / "platform.db", synchronous=config.platform.sqlite_synchronous)
    registry.initialize()
    metrics = PlatformMetrics()
    workspaces = WorkspaceManager(config.storage.workspace_root, config.storage.state_root, runtime_uid=10001, runtime_gid=10001)
    backend = LocalDockerBackend(config, registry, workspaces, agents_root, metrics=metrics)
    upstream = httpx.AsyncClient(trust_env=False, timeout=config.model_gateway.request_timeout_seconds)
    monitor = HealthMonitor(backend, upstream, metrics)
    management = None
    management_routers = []
    token_path = Path(config.platform.data_root) / 'admin-token'
    if token_path.is_file():
        from app.management import ManagementStore
        from app.management_runtime import ManagementRuntime
        from app.admin_api import create_admin_router
        store = ManagementStore(Path(config.platform.data_root) / 'management', agents_root)
        management = ManagementRuntime(store, backend, upstream)
        backend.management = management
        management_routers.append(create_admin_router(store, management))

    @asynccontextmanager
    async def lifespan(application):
        with registry.lifetime():
            task = None
            try:
                if management:
                    await management.recover()
                application.state.recovery = await backend.reconcile()
                emit("startup_reconciled", component="controller")
                task = asyncio.create_task(monitor.run())
                yield
            finally:
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                if management:
                    await management.close()
                await upstream.aclose()
                backend.client.close()

    application = create_app(
        create_gateway_router(registry, backend, upstream, metrics=metrics),
        cloud_routers=[create_health_router(monitor), create_auth_router(config.auth), create_files_router(config.storage, workspaces, metrics=metrics), *management_routers],
        metrics=metrics, lifespan=lifespan, metrics_enabled=config.metrics.enabled,
        metrics_path=config.metrics.prometheus_path,
    )
    application.state.backend = backend
    application.state.health_monitor = monitor
    if management:
        from app.admin_auth import AdminAuthMiddleware
        token = token_path.read_text().strip()
        if len(token) < 32:
            raise RuntimeError('Administrator token must contain at least 32 characters')
        application.add_middleware(AdminAuthMiddleware, token=token)
        application.state.management = management
        original_openapi = application.openapi
        def management_openapi():
            schema = original_openapi()
            schema.setdefault('components', {}).setdefault('securitySchemes', {})['AdminBearer'] = {
                'type': 'http', 'scheme': 'bearer', 'description': 'Single administrator credential generated at installation'}
            for path, operations in schema.get('paths', {}).items():
                if path != '/cloud/health':
                    for operation in operations.values():
                        if isinstance(operation, dict):
                            operation['security'] = [{'AdminBearer': []}]
            return schema
        application.openapi = management_openapi
    return application


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--config", type=Path, default=Path("config.cfg"))
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.check_config:
        print(json.dumps(config.safe_dict(), indent=2))
        return
    configure_logging(config.platform.log_level)
    application = build_app(config, args.config.resolve().parent / "agents")
    uvicorn.run(application, host=args.host or config.platform.host, port=args.port or config.platform.port,
                log_config=None, access_log=False)


if __name__ == "__main__":
    main()
