import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx


def service_config(tmp_path: Path) -> dict[str, Any]:
    return {
        "data_root": str(tmp_path / "manager"),
        "log_root": str(tmp_path / "logs"),
        "port": 8102,
        "service_token": "service",
        "settings": {"model_gateway_public_url": "http://model.test/v1"},
        "services": {
            name: f"http://{name}.test"
            for name in (
                "catalog_service",
                "file_service",
                "model_gateway",
                "operations",
            )
        },
    }


def patch_http_clients(
    monkeypatch,
    handler: Callable[[httpx.Request], httpx.Response],
    async_handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> None:
    original_sync, original_async = httpx.Client, httpx.AsyncClient

    def factory(client_type, transport):
        def create(*args, **kwargs):
            kwargs["transport"] = transport
            return client_type(*args, **kwargs)

        return create

    monkeypatch.setattr(httpx, "Client", factory(original_sync, httpx.MockTransport(handler)))
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        factory(original_async, httpx.MockTransport(async_handler or handler)),
    )


def disable_health_monitor(monkeypatch, service) -> None:
    async def wait_forever(_monitor):
        await asyncio.Event().wait()

    monkeypatch.setattr(service.HealthMonitor, "run", wait_forever)
