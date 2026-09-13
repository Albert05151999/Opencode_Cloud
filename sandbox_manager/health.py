"""Dependency readiness and non-destructive sandbox health/idle monitoring."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter
from starlette.responses import JSONResponse

from shared_libs.metrics import PlatformMetrics
from sandbox_manager.backend import LocalDockerBackend

logger = logging.getLogger(__name__)
_tick_catalog = ContextVar("health_tick_catalog", default=None)


class HealthMonitor:
    def __init__(
        self,
        backend: LocalDockerBackend,
        client: httpx.AsyncClient,
        metrics: PlatformMetrics,
    ) -> None:
        self.backend, self.client, self.metrics = backend, client, metrics
        self.failures: dict[str, int] = {}
        self._tick_lock = asyncio.Lock()

    async def model_health(self) -> bool:
        try:
            response = await self.client.get(
                self.backend.config.model_gateway.health_url, timeout=3
            )
            healthy = response.is_success
        except httpx.HTTPError:
            healthy = False
        self.metrics.model_health.set(int(healthy))
        return healthy

    async def readiness(self) -> dict[str, bool]:
        def local_checks():
            result = {}
            checks = {
                "sqlite": self._sqlite,
                "docker": self.backend.client.ping,
                "image": lambda: self.backend.client.images.get(
                    self.backend.config.sandbox.image
                ),
                "workspace": self._workspace,
            }
            for name, check in checks.items():
                try:
                    result[name] = check() is not False
                except Exception:
                    result[name] = False
            return result

        local, model = await asyncio.gather(
            asyncio.to_thread(local_checks), self.model_health()
        )
        return {**local, "model_gateway": model}

    def _sqlite(self):
        with self.backend.registry.connect() as connection:
            connection.execute("SELECT COUNT(*) FROM sandboxes").fetchone()

    def _workspace(self):
        root = Path(self.backend.config.storage.workspace_root)
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=root) as handle:
            handle.write(b"health")
            handle.flush()

    async def tick(self, *, now: datetime | None = None) -> None:
        async with self._tick_lock:
            dependencies_healthy = await self.model_health()
            records = await asyncio.to_thread(self.backend.registry.list_sandboxes)
            if not records:
                return
            snapshots = iter(records)

            async def worker() -> None:
                for snapshot in snapshots:
                    try:
                        await self._check_sandbox(snapshot, now)
                    except Exception:
                        logger.exception(
                            "sandbox health check failed for %s", snapshot.sandbox_id
                        )

            # Four workers bound slow Docker operations without serializing the
            # complete health pass behind one sandbox.
            token = _tick_catalog.set({})
            try:
                await asyncio.gather(*(worker() for _ in range(min(4, len(records)))))
            finally:
                tasks = list(_tick_catalog.get().values())
                if tasks:
                    pending = asyncio.gather(*tasks, return_exceptions=True)
                    while not pending.done():
                        try:
                            await asyncio.shield(pending)
                        except asyncio.CancelledError:
                            continue
                _tick_catalog.reset(token)
            management = getattr(self.backend, "management", None)
            if management and hasattr(
                getattr(management, "operations", None), "recovery"
            ):
                await management.operations.recovery.tick(
                    dependencies_healthy, self.failures
                )

    async def _idle_definition(self, agent_id):
        cache = _tick_catalog.get()
        if cache is None or not hasattr(self.backend.registry, "connect"):
            return await asyncio.to_thread(self.backend.agent_catalog.load, agent_id)
        def registered_path():
            with self.backend.registry.connect() as db:
                row = db.execute("SELECT config_path FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
                return str(Path(row[0]).resolve()) if row else None
        path = await asyncio.to_thread(registered_path)
        key = (agent_id, path)
        if key not in cache:
            cache[key] = asyncio.create_task(asyncio.to_thread(self.backend.agent_catalog.load, agent_id))
        definition = await asyncio.shield(cache[key])
        # A publication may have changed the registry while the remote read waited.
        current_path = await asyncio.to_thread(registered_path)
        if current_path != path:
            return await self._idle_definition(agent_id)
        if path is None or str(definition.path.resolve()) != path:
            raise RuntimeError("Agent publication snapshot changed; defer idle eviction")
        return definition

    async def _check_sandbox(self, snapshot, now: datetime | None) -> None:
        management = getattr(self.backend, "management", None)
        if (
            management
            and hasattr(management, "load_tests")
            and await asyncio.to_thread(
                management.load_tests.active_user, snapshot.agent_id, snapshot.username
            )
        ):
            return  # The load runner owns lifecycle until its report is final.
        if management and (
            snapshot.agent_id in management.blocked or "*" in management.blocked
        ):
            return
        if not snapshot.container_id:
            return
        key = (snapshot.agent_id, snapshot.username)
        lock = self.backend._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if management and (snapshot.agent_id in management.blocked or "*" in management.blocked):
                return
            record = await asyncio.to_thread(self.backend.registry.get_sandbox, *key)
            if record is None or record.status not in {"ready", "unhealthy", "stopped"}:
                return
            elapsed = (
                (now or datetime.now(timezone.utc))
                - datetime.fromisoformat(record.last_active_at)
            ).total_seconds()
            definition = await self._idle_definition(record.agent_id)
            timeout = definition.idle_timeout_seconds
            # Retry deletion after a previous stop succeeded but removal failed.
            if elapsed >= timeout and not self.backend.in_use.get(record.sandbox_id, 0):
                stopped = await self.backend._get_container(record.container_id)
                if stopped is not None:
                    self.backend._verify_ownership(stopped, *key)
                    if stopped.status in {"exited", "created", "dead"}:
                        await self._remove_idle_container(record, stopped)
                        return
            if record.status == "stopped":
                observed = await self.backend._get_container(record.container_id)
                if observed is not None:
                    self.backend._verify_ownership(observed, *key)
                    if observed.status in {"exited", "created", "dead"}:
                        self.failures.pop(record.sandbox_id, None)
                        return
            try:
                endpoint = await self.backend.inspect(*key)
                if endpoint is None:
                    raise RuntimeError("sandbox is no longer running")
                payload = await self.backend._health_probe(
                    endpoint.base_url + self.backend.config.opencode.health_path,
                    2,
                )
                if (
                    payload.get("healthy") is not True
                    or payload.get("version")
                    != self.backend.config.opencode.expected_version
                ):
                    raise RuntimeError("OpenCode health/version mismatch")
            except Exception:
                self.metrics.sandbox_health_failures.inc()
                self.failures[record.sandbox_id] = (
                    self.failures.get(record.sandbox_id, 0) + 1
                )
                if (
                    self.failures[record.sandbox_id]
                    >= self.backend.config.sandbox.health_failure_threshold
                ):
                    await asyncio.to_thread(
                        self.backend.registry.set_health_status,
                        record.sandbox_id,
                        "unhealthy",
                    )
                return
            self.failures.pop(record.sandbox_id, None)
            if record.status in {"unhealthy", "stopped"}:
                await asyncio.to_thread(
                    self.backend.registry.set_health_status, record.sandbox_id, "ready"
                )
            if self.backend.in_use.get(record.sandbox_id, 0):
                await asyncio.to_thread(
                    self.backend.registry.touch_sandbox, record.sandbox_id
                )
                return
            elapsed = (
                (now or datetime.now(timezone.utc))
                - datetime.fromisoformat(record.last_active_at)
            ).total_seconds()

            if elapsed < timeout:
                return
            # Native prompt_async work can outlive its HTTP request.
            try:
                from sandbox_manager.session_binding import directory_collection

                sessions = await directory_collection(
                    self.client, self.backend.registry, endpoint, timeout=2
                )
                if not isinstance(sessions, dict) or any(
                    value.get("type") != "idle" for value in sessions.values()
                ):
                    await asyncio.to_thread(
                        self.backend.registry.touch_sandbox, record.sandbox_id
                    )
                    return
            except (httpx.HTTPError, ValueError, AttributeError):
                return
            container = await self.backend._get_container(record.container_id)
            if container is None:
                return
            self.backend._verify_ownership(container, *key)
            await asyncio.to_thread(container.stop, timeout=10)
            await self._remove_idle_container(record, container)

    async def _remove_idle_container(self, record, container):
        await asyncio.to_thread(container.remove)
        await asyncio.to_thread(
            self.backend.registry.upsert_sandbox,
            sandbox_id=record.sandbox_id,
            agent_id=record.agent_id,
            username=record.username,
            container_id=None,
            host_port=None,
            status="stopped",
            image_version=record.image_version,
            last_active_at=record.last_active_at,
        )
        self.failures.pop(record.sandbox_id, None)
        self.metrics.sandbox_evictions.inc()

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("health monitor tick failed")
            await asyncio.sleep(self.backend.config.sandbox.health_interval_seconds)


def create_health_router(monitor: HealthMonitor) -> APIRouter:
    router = APIRouter()

    @router.get("/cloud/health/ready")
    async def readiness():
        checks = await monitor.readiness()
        ready = all(checks.values())
        return JSONResponse(
            {"ok": ready, "checks": checks}, status_code=200 if ready else 503
        )

    return router
