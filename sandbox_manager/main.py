"""Owned Docker execution API and native session routing service."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException

from sandbox_manager.backend import LocalDockerBackend, SandboxEndpoint, SandboxError
from sandbox_manager.capacity import LoadCapacity
from sandbox_manager.catalog_client import Admission, RemoteCatalog, install_bundle
from sandbox_manager.configuration import backend_config
from sandbox_manager.health import HealthMonitor
from sandbox_manager.native_router import create_gateway_router
from sandbox_manager.probes import ProbeRunner
from sandbox_manager.registry import Registry
from sandbox_manager.session_binding import directory_collection
from sandbox_manager.workspace_client import RemoteWorkspaces
from shared_libs.metrics import PlatformMetrics
from shared_libs.service import configure_service, internal_client, run, settings
from shared_libs.validation import relative_file
from shared_libs.workspace_paths import validate_identifier


def create_app(config=None, backend=None):
    config = config or settings("sandbox_manager")
    root = Path(config["data_root"])
    root.mkdir(parents=True, exist_ok=True)
    typed = backend_config(config)
    agents_root = Path(
        os.environ.get(
            "AGENTS_ROOT",
            config.get("settings", {}).get("agents_root", str(root / "agents")),
        )
    )
    agents_root.mkdir(parents=True, exist_ok=True)
    registry = backend.registry if backend else Registry(root / "platform.db")
    registry.initialize()
    metrics = PlatformMetrics()
    client = httpx.AsyncClient(trust_env=False, timeout=120)
    ops = internal_client(config, "operations")
    files = internal_client(config, "file_service")
    admission = Admission(config)
    journal_path = root / "lifecycle.db"
    with sqlite3.connect(journal_path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS blocks(agent TEXT PRIMARY KEY)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS verified(agent TEXT PRIMARY KEY, version TEXT)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, payload TEXT, result TEXT)"
        )
        admission.blocked.update(x[0] for x in db.execute("SELECT agent FROM blocks"))
    state = {"backend": backend, "error": None, "monitor": None, "capacity": None}
    locks = {}

    @asynccontextmanager
    async def lifespan(app):
        monitor_task = None
        initialized = False

        async def runtime_health(url, timeout):
            # Reuse the lifespan-owned native HTTP pool; still probe every acquire.
            response = await client.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()

        async def initialize():
            nonlocal monitor_task, initialized
            if initialized:
                return
            if state["backend"] is None:
                workspaces = RemoteWorkspaces(
                    config, typed.storage.workspace_root, typed.storage.state_root
                )
                try:
                    state["backend"] = await asyncio.to_thread(
                        LocalDockerBackend,
                        typed,
                        registry,
                        workspaces,
                        agents_root,
                        health_probe=runtime_health,
                        metrics=metrics,
                    )
                except Exception:
                    workspaces.client.close()
                    raise
            b = state["backend"]
            b.management = admission
            if not isinstance(getattr(b, "agent_catalog", None), RemoteCatalog):
                b.agent_catalog = RemoteCatalog(
                    config, agents_root, typed.model_gateway.base_url
                )
            if hasattr(b, "reconcile"):
                await b.reconcile()
            state["monitor"] = HealthMonitor(b, client, metrics)
            app.include_router(
                create_gateway_router(registry, b, client, metrics=metrics)
            )
            monitor_task = asyncio.create_task(state["monitor"].run())
            state["error"] = None
            initialized = True

        async def attempt():
            try:
                await initialize()
            except Exception as exc:
                state["error"] = type(exc).__name__

        async def retry():
            while not initialized:
                await asyncio.sleep(5)
                await attempt()

        await attempt()
        retry_task = asyncio.create_task(retry())
        try:
            yield
        finally:
            for task in (retry_task, monitor_task):
                if task:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            await client.aclose()
            await ops.aclose()
            await files.aclose()
            admission.catalog.close()
            admission.control.close()
            if state["backend"] is not None:
                b = state["backend"]
                b.client.close()
                for value in (
                    getattr(b, "agent_catalog", None),
                    getattr(b, "workspaces", None),
                ):
                    if getattr(value, "client", None):
                        value.client.close()

    application = FastAPI(title="Sandbox manager", lifespan=lifespan)
    configure_service(application, "sandbox_manager", config, metrics=metrics)
    application.state.runtime = state

    def current():
        if state["backend"] is None:
            raise HTTPException(
                503, "Docker backend unavailable: " + str(state["error"])
            )
        return state["backend"]

    @application.get("/health/ready")
    async def ready():
        try:
            b = current()
            if state["error"] or state["monitor"] is None:
                raise HTTPException(503, "Backend initialization incomplete")
            await asyncio.to_thread(b.client.ping)
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(503, "Docker backend not ready") from exc

    @application.get("/internal/v1/runtime-security")
    async def runtime_security():
        backend = current()
        rows = []
        for record in registry.list_sandboxes():
            row = {
                "sandbox_id": record.sandbox_id,
                "agent_id": record.agent_id,
                "container_id": record.container_id,
                "status": "unknown",
                "checks": {},
                "issues": [],
            }
            try:
                container = (
                    await backend._get_container(record.container_id)
                    if record.container_id
                    else None
                )
                if container is None:
                    row.update(
                        status="absent", reason="No recorded owned container exists"
                    )
                    rows.append(row)
                    continue
                backend._verify_ownership(container, record.agent_id, record.username)
                if hasattr(container, "reload"):
                    await asyncio.to_thread(container.reload)
                attrs = getattr(container, "attrs", {})
                host = attrs.get("HostConfig") or {}
                checks = {
                    "privileged": host.get("Privileged"),
                    "read_only_rootfs": host.get("ReadonlyRootfs"),
                    "host_network": host.get("NetworkMode") == "host"
                    if "NetworkMode" in host
                    else None,
                    "added_capabilities": host.get("CapAdd"),
                    "no_new_privileges": any(str(value) in {"no-new-privileges", "no-new-privileges:true"} for value in (host.get("SecurityOpt") or [])) if "SecurityOpt" in host else None,
                    "drop_all_capabilities": "ALL" in (host.get("CapDrop") or [])
                    if "CapDrop" in host
                    else None,
                    "cpu_limit": host.get("NanoCpus", 0) / 1e9
                    if "NanoCpus" in host
                    else None,
                    "memory_limit_bytes": host.get("Memory"),
                    "pids_limit": host.get("PidsLimit"),
                }
                if (
                    not checks["cpu_limit"]
                    and host.get("CpuQuota", 0) > 0
                    and host.get("CpuPeriod", 0) > 0
                ):
                    checks["cpu_limit"] = host["CpuQuota"] / host["CpuPeriod"]
                issues = []
                for field, bad in (
                    ("privileged", True),
                    ("read_only_rootfs", False),
                    ("host_network", True),
                    ("drop_all_capabilities", False),
                    ("no_new_privileges", False),
                ):
                    if checks[field] is bad:
                        issues.append(field)
                if checks["added_capabilities"]:
                    issues.append("added_capabilities")
                for field in ("cpu_limit", "memory_limit_bytes", "pids_limit"):
                    if checks[field] is not None and checks[field] <= 0:
                        issues.append(field)
                unknown = [
                    name
                    for name, value in checks.items()
                    if value is None and name != "added_capabilities"
                ]
                # Docker represents an explicitly empty CapAdd as null. Missing
                # inspection keys remain unknown rather than passing silently.
                if "CapAdd" not in host:
                    unknown.append("added_capabilities")
                row.update(
                    status="issues" if issues else "unknown" if unknown else "ok",
                    checks=checks,
                    issues=issues,
                    unknown_checks=unknown,
                    container_state=getattr(container, "status", "unknown"),
                    image=(attrs.get("Config") or {}).get(
                        "Image", record.image_version
                    ),
                )
            except Exception:
                row.update(
                    status="unknown",
                    reason="Owned container inspection or ownership validation failed",
                )
            rows.append(row)
        return {
            "scope": "managed_sandboxes",
            "sampled_at": time.time(),
            "containers": rows,
            "summary": {
                "checked": len(rows),
                "with_issues": sum(r["status"] == "issues" for r in rows),
                "unknown": sum(r["status"] == "unknown" for r in rows),
            },
        }

    @application.get("/internal/v1/capacity")
    async def capacity():
        if state["capacity"] is None:
            state["capacity"] = LoadCapacity(current())
        return await state["capacity"].snapshot()

    @application.get("/internal/v1/sandboxes")
    def list_sandboxes(
        agent_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
        q: str = "",
        status: str | None = None,
    ):
        items = [
            asdict(r)
            for r in registry.list_sandboxes()
            if (not agent_id or r.agent_id == agent_id)
            and (not status or r.status == status)
        ]
        if q:
            items = [r for r in items if q.lower() in json.dumps(r).lower()]
        return {
            "total": len(items),
            "items": items[max(0, offset) : max(0, offset) + min(200, max(1, limit))],
        }

    def active_request_leases(backend, sid):
        return max(0, backend.in_use.get(sid, 0)
                   - getattr(backend, "event_subscribers", {}).get(sid, 0))

    async def execution(record):
        b = current()
        if (
            active_request_leases(b, record.sandbox_id)
            or admission.requests.get(record.agent_id)
            or admission.acquiring.get(record.agent_id)
        ):
            return "busy"
        try:
            endpoint = await b.inspect(record.agent_id, record.username)
            if endpoint is None:
                # A missing route is not evidence that an owned process stopped.
                # Inspect both its recorded ID and deterministic Docker name.
                key = hashlib.sha256(
                    (record.agent_id + "\x00" + record.username).encode()
                ).hexdigest()[:20]
                if hasattr(b, "_find_existing"):
                    container = await b._find_existing(
                        record, key, record.agent_id, record.username
                    )
                else:
                    container = (
                        await b._get_container(record.container_id)
                        if record.container_id
                        else None
                    )
                if container is None:
                    return "idle"
                b._verify_ownership(container, record.agent_id, record.username)
                if hasattr(container, "reload"):
                    await asyncio.to_thread(container.reload)
                # paused/restarting/unknown containers may resume execution.
                return (
                    "idle"
                    if getattr(container, "status", None)
                    in {"created", "exited", "dead"}
                    else "unknown"
                )
            statuses = await directory_collection(client, registry, endpoint)
            if not isinstance(statuses, dict):
                return "unknown"
            types = [
                v.get("type") if isinstance(v, dict) else None
                for v in statuses.values()
            ]
            if any(value in {"busy", "retry"} for value in types):
                return "busy"
            return "idle" if all(value == "idle" for value in types) else "unknown"
        except (httpx.HTTPError, ValueError, SandboxError):
            return "unknown"

    @application.get("/internal/v1/sandboxes/by-owner/{agent_id}/{username}")
    async def detail(agent_id: str, username: str):
        backend = current()
        async with backend._locks.setdefault((agent_id, username), asyncio.Lock()):
            record = registry.get_sandbox(agent_id, username)
            if not record:
                raise HTTPException(404, "Sandbox not found")
            container_state = "unknown"
            try:
                key = hashlib.sha256((agent_id + "\x00" + username).encode()).hexdigest()[:20]
                container = await backend._find_existing(record, key, agent_id, username)
                if container is None:
                    container_state = "absent"
                else:
                    backend._verify_ownership(container, agent_id, username)
                    if hasattr(container, "reload"):
                        await asyncio.to_thread(container.reload)
                    container_state = getattr(container, "status", "unknown")
                    if container_state in {"exited", "dead", "created"}:
                        # Observation needs no admission grant; the same user lock
                        # prevents a concurrent start from being overwritten.
                        registry.mark_sandbox_status(record.sandbox_id, "stopped")
                        record = registry.get_sandbox(agent_id, username)
            except Exception:
                # Foreign or unavailable Docker state is never evidence of stop.
                container_state = "unknown"
            return {
                **asdict(record),
                "execution": "unknown" if container_state == "unknown" else await execution(record),
                "activity_generation": record.last_active_at,
                "container_state": container_state,
                "sessions": len(registry.list_sessions_for_sandbox(record.sandbox_id)),
                "active_request_leases": active_request_leases(backend, record.sandbox_id),
                "event_subscriptions": getattr(backend, "event_subscribers", {}).get(record.sandbox_id, 0),
            }

    def by_sid(sid):
        record = next(
            (r for r in registry.list_sandboxes() if r.sandbox_id == sid), None
        )
        if record is None:
            raise HTTPException(404, "Sandbox not found")
        return record

    @application.get("/internal/v1/sandboxes/{sid}")
    async def detail_sid(sid: str):
        r = by_sid(sid)
        result = await detail(r.agent_id, r.username)
        sessions = registry.list_sessions_for_sandbox(sid)
        result.update(
            session_count=len(sessions),
            sessions=[
                {**asdict(x), "execution": {"type": "idle" if result["execution"] == "idle" else "unknown"}} for x in sessions
            ],
            cpu_percent=None,
            memory_bytes=None,
            sampled_at=time.time(),
            configuration_version=None,
        )
        with registry.connect() as db:
            row = db.execute(
                "SELECT config_path FROM agents WHERE agent_id=?", (r.agent_id,)
            ).fetchone()
        if row:
            result["configuration_version"] = Path(row[0]).parent.name
        b = current()
        try:
            container = (
                await b._get_container(r.container_id) if r.container_id else None
            )
            if container:
                b._verify_ownership(container, r.agent_id, r.username)
                stats = await asyncio.wait_for(
                    asyncio.to_thread(container.stats, stream=False, one_shot=True), 3
                )
                result["memory_bytes"] = stats.get("memory_stats", {}).get("usage")
                cpu = stats.get("cpu_stats", {})
                old = stats.get("precpu_stats", {})
                total = cpu.get("cpu_usage", {}).get("total_usage", 0) - old.get(
                    "cpu_usage", {}
                ).get("total_usage", 0)
                system = cpu.get("system_cpu_usage", 0) - old.get("system_cpu_usage", 0)
                if system > 0 and total >= 0:
                    result["cpu_percent"] = round(
                        total / system * cpu.get("online_cpus", 1) * 100, 2
                    )
        except Exception:
            pass
        return result

    previews = {}

    @application.get("/internal/v1/sandboxes/{sid}/force-preview")
    async def force_preview(sid: str):
        r = by_sid(sid)
        pid = uuid.uuid4().hex
        result = {
            "preview_id": pid,
            "expires": time.time() + 300,
            "sandbox_id": sid,
            "container_id": r.container_id,
            "activity_generation": r.last_active_at,
            "sessions": [asdict(s) for s in registry.list_sessions_for_sandbox(sid)],
            "execution": await execution(r),
        }
        previews[pid] = result
        return result

    @application.post("/internal/v1/sandboxes/{sid}/actions")
    async def sandbox_action(sid: str, body: dict):
        r, backend = by_sid(sid), current()
        name, key = body.get("action"), body.get("request_id")
        if name not in {"start", "stop", "restart", "recover", "destroy"}:
            raise HTTPException(400, "Invalid sandbox action")
        if not isinstance(key, str) or not key or len(key) > 256:
            raise HTTPException(400, "A bounded request_id is required")
        canonical = json.dumps(
            {"resource": "sandbox", "sandbox_id": sid, **body}, sort_keys=True
        )
        async with backend._locks.setdefault((r.agent_id, r.username), asyncio.Lock()):
            with sqlite3.connect(journal_path) as db:
                old = db.execute(
                    "SELECT payload,result FROM commands WHERE id=?", (key,)
                ).fetchone()
            if old:
                if old[0] != canonical:
                    raise HTTPException(409, "Idempotency key reused")
                if old[1] is None:
                    raise HTTPException(
                        409, "Prior action interrupted; reconcile before retry"
                    )
                return json.loads(old[1])
            r = by_sid(sid)
            if (
                body.get("expected_container_id") is not None
                and body["expected_container_id"] != r.container_id
            ):
                raise HTTPException(409, "Container changed")
            if (
                body.get("expected_activity_generation") is not None
                and body["expected_activity_generation"] != r.last_active_at
            ):
                raise HTTPException(409, "Activity changed")
            observed = await execution(r)
            if body.get("force"):
                preview = previews.get(body.get("preview_id"))
                if (
                    not preview
                    or preview["sandbox_id"] != sid
                    or preview["expires"] < time.time()
                    or preview["container_id"] != r.container_id
                    or preview["activity_generation"] != r.last_active_at
                ):
                    raise HTTPException(409, "Force preview expired or changed")
            elif name != "start" and (active_request_leases(backend, sid) or observed != "idle"):
                raise HTTPException(409, "Sandbox execution is not confirmed idle")
            # Check resource/admission policy before destroying a container. This
            # deliberately uses the resource check, not check_acquire: the latter
            # also rejects the coordinator's own publication block.
            if name in {"start", "restart", "recover"}:
                await asyncio.to_thread(admission.resources_for, r.agent_id, r.username)
            container = (
                await backend._get_container(r.container_id) if r.container_id else None
            )
            if name == "destroy" and container is None and hasattr(backend, "_find_existing"):
                sandbox_key = hashlib.sha256(
                    (r.agent_id + "\x00" + r.username).encode()
                ).hexdigest()[:20]
                container = await backend._find_existing(
                    r, sandbox_key, r.agent_id, r.username
                )
            if container:
                backend._verify_ownership(container, r.agent_id, r.username)
            # Reserve the command under a database write lock, including across
            # service replicas. An interrupted execution is never replayed.
            with sqlite3.connect(journal_path) as db:
                db.execute("BEGIN IMMEDIATE")
                old = db.execute(
                    "SELECT payload,result FROM commands WHERE id=?", (key,)
                ).fetchone()
                if old:
                    if old[0] != canonical or old[1] is None:
                        raise HTTPException(
                            409, "Command is already executing or its identity changed"
                        )
                    return json.loads(old[1])
                db.execute("INSERT INTO commands VALUES(?,?,NULL)", (key, canonical))
            if body.get("force"):
                previews.pop(body["preview_id"], None)
            if name == "destroy":
                if container:
                    await backend._remove_owned(container)
                # Keep session routes and mounted workspace/state; acquire recreates
                # the runtime on the next request without losing conversation history.
                registry.upsert_sandbox(sandbox_id=sid, agent_id=r.agent_id,
                    username=r.username, container_id=None, host_port=None,
                    status="destroyed", image_version=r.image_version)
            elif name == "stop":
                if container:
                    await asyncio.to_thread(container.stop, timeout=10)
                registry.mark_sandbox_status(sid, "stopped")
            elif name in {"restart", "recover"}:
                if container:
                    await backend._remove_owned(container)
                await backend._acquire_locked(r.agent_id, r.username)
            else:
                await backend._acquire_locked(r.agent_id, r.username)
            result = {"ok": True, "sandbox_id": sid, "action": name}
            with sqlite3.connect(journal_path) as db:
                db.execute(
                    "UPDATE commands SET result=? WHERE id=?", (json.dumps(result), key)
                )
            return result

    def impact(aid):
        validate_identifier(aid, "agent_id")
        records = [asdict(r) for r in registry.list_sandboxes() if r.agent_id == aid]
        sessions = [
            asdict(s)
            for r in records
            for s in registry.list_sessions_for_sandbox(r["sandbox_id"])
        ]
        return {
            "sandboxes": [r["sandbox_id"] for r in records],
            "sessions": len(sessions),
            "fingerprint": hashlib.sha256(
                json.dumps([records, sessions], sort_keys=True).encode()
            ).hexdigest(),
        }

    @application.get("/internal/v1/agents/{aid}/deletion-impact")
    def deletion_impact(aid: str):
        return impact(aid)

    @application.get("/internal/v1/agents/{aid}/application-status")
    async def application_status(aid: str):
        validate_identifier(aid, "agent_id")
        catalog = current().agent_catalog
        definition = await asyncio.to_thread(catalog.load, aid)
        version = definition.path.parent.name
        with sqlite3.connect(journal_path) as db:
            row = db.execute(
                "SELECT version FROM verified WHERE agent=?", (aid,)
            ).fetchone()
        return {
            "version": version,
            "staged": aid in catalog.overrides,
            "verified": bool(row and row[0] == version),
            "blocked": aid in admission.blocked or "*" in admission.blocked,
        }

    async def drain(aid, timeout=120):
        deadline = time.monotonic() + timeout
        while True:
            records = [
                r for r in registry.list_sandboxes() if aid == "*" or r.agent_id == aid
            ]
            status = await asyncio.gather(*(execution(r) for r in records))
            requests = (
                sum(admission.requests.values())
                if aid == "*"
                else admission.requests.get(aid, 0)
            )
            acquiring = (
                sum(admission.acquiring.values())
                if aid == "*"
                else admission.acquiring.get(aid, 0)
            )
            if not requests and not acquiring and all(x == "idle" for x in status):
                return
            if time.monotonic() >= deadline:
                raise HTTPException(
                    409, "Could not confirm sandbox idle before operation"
                )
            await asyncio.sleep(0.5)

    async def remove_records(aid, username=None, load_test=None):
        b = current()
        removed = []
        for record in registry.list_sandboxes():
            if record.agent_id != aid or (username and record.username != username):
                continue
            if active_request_leases(b, record.sandbox_id):
                raise HTTPException(409, "Sandbox has active leases")
            container = (
                await b._get_container(record.container_id)
                if record.container_id
                else None
            )
            if container:
                b._verify_ownership(container, aid, record.username)
                if (
                    load_test
                    and container.attrs.get("Config", {})
                    .get("Labels", {})
                    .get("cloud.load_test")
                    != load_test
                ):
                    raise HTTPException(409, "Load-test ownership changed")
                await b._remove_owned(container)
            registry.mark_sandbox_status(record.sandbox_id, "missing")
            removed.append(record.sandbox_id)
        return removed

    @application.post("/internal/v1/agents/{aid}/actions")
    async def action(aid: str, body: dict):
        if aid != "*":
            validate_identifier(aid, "agent_id")
        name = body.get("action")
        if aid == "*" and name not in {"quiesce", "resume", "verify"}:
            raise HTTPException(400, "Global action not allowed")
        if name not in {
            "quiesce",
            "apply",
            "verify",
            "resume",
            "archive",
            "restore",
            "delete",
            "restart",
            "stop",
        }:
            raise HTTPException(400, "Unknown lifecycle action")
        key = body.get("request_id")
        canonical = json.dumps({"aid": aid, **body}, sort_keys=True)
        async with locks.setdefault(aid, asyncio.Lock()):
            if key:
                with sqlite3.connect(journal_path) as db:
                    old = db.execute(
                        "SELECT payload,result FROM commands WHERE id=?", (key,)
                    ).fetchone()
                    if old:
                        if old[0] != canonical:
                            raise HTTPException(409, "Idempotency key reused")
                        if old[1] is None:
                            raise HTTPException(
                                409, "Prior action interrupted; reconcile before retry"
                            )
                        return json.loads(old[1])
                    db.execute(
                        "INSERT INTO commands VALUES(?,?,NULL)", (key, canonical)
                    )
            result = {"ok": True, "action": name, "agent_id": aid}
            if name == "resume" or name == "restore":
                if name == "resume":
                    for target in (
                        list(current().agent_catalog.overrides)
                        if aid == "*"
                        else ([aid] if aid in current().agent_catalog.overrides else [])
                    ):
                        await asyncio.to_thread(current().agent_catalog.commit, target)
                admission.blocked.discard(aid)
                with sqlite3.connect(journal_path) as db:
                    db.execute("DELETE FROM blocks WHERE agent=?", (aid,))
            elif name == "verify":
                b = current()
                targets = list(b.agent_catalog.overrides) if aid == "*" else [aid]
                for target in targets:
                    definition = await asyncio.to_thread(b.agent_catalog.load, target)
                    for record in registry.list_sandboxes():
                        if record.agent_id == target:
                            desired = await ops.get(
                                "/internal/v1/sandboxes/"
                                + record.sandbox_id
                                + "/desired-state"
                            )
                            if desired.is_error:
                                raise HTTPException(
                                    503, "Cannot verify sandbox desired state"
                                )
                            if desired.json().get("state") == "stopped":
                                continue
                            async with b._locks.setdefault(
                                (target, record.username), asyncio.Lock()
                            ):
                                await b._acquire_locked(target, record.username)
                    with sqlite3.connect(journal_path) as db:
                        db.execute(
                            "INSERT OR REPLACE INTO verified VALUES(?,?)",
                            (target, definition.path.parent.name),
                        )
                result["records"] = [
                    asdict(r)
                    for r in registry.list_sandboxes()
                    if aid == "*" or r.agent_id == aid
                ]
                result["verified"] = True
            else:
                if (
                    body.get("expected_fingerprint")
                    and impact(aid)["fingerprint"] != body["expected_fingerprint"]
                ):
                    raise HTTPException(409, "Deletion impact changed")
                admission.blocked.add(aid)
                with sqlite3.connect(journal_path) as db:
                    db.execute("INSERT OR IGNORE INTO blocks VALUES(?)", (aid,))
                await drain(aid, min(120, float(body.get("timeout", 120))))
                if (
                    body.get("expected_fingerprint")
                    and impact(aid)["fingerprint"] != body["expected_fingerprint"]
                ):
                    raise HTTPException(409, "Deletion impact changed while draining")
                if name == "apply":
                    with sqlite3.connect(journal_path) as db:
                        db.execute("DELETE FROM verified WHERE agent=?", (aid,))
                    bundle = body.get("bundle", {})
                    path = install_bundle(agents_root, aid, bundle)
                    current().agent_catalog.stage(aid, path)
                if name in {"apply", "archive", "delete", "restart", "stop"}:
                    result["removed"] = await remove_records(aid, body.get("username"))
                if name == "delete":
                    with registry._write_connection() as db:
                        db.execute("DELETE FROM sessions WHERE agent_id=?", (aid,))
                        db.execute("DELETE FROM sandboxes WHERE agent_id=?", (aid,))
                        db.execute("DELETE FROM agents WHERE agent_id=?", (aid,))
            if key:
                with sqlite3.connect(journal_path) as db:
                    db.execute(
                        "UPDATE commands SET result=? WHERE id=?",
                        (json.dumps(result), key),
                    )
            return result

    @application.post("/internal/v1/load-tests/{rid}/users/{aid}/{username}/cleanup")
    async def cleanup(rid: str, aid: str, username: str):
        validate_identifier(aid, "agent_id")
        validate_identifier(username, "username")
        async with current()._locks.setdefault((aid, username), asyncio.Lock()):
            record = registry.get_sandbox(aid, username)
            result = await remove_records(aid, username, load_test=rid)
            if record:
                with registry._write_connection() as db:
                    db.execute(
                        "DELETE FROM sessions WHERE sandbox_id=?", (record.sandbox_id,)
                    )
                    db.execute(
                        "DELETE FROM sandboxes WHERE sandbox_id=?", (record.sandbox_id,)
                    )
            return {"ok": True, "removed": result}

    @application.post("/internal/v1/probes")
    async def probe(body: dict):
        aid = "probe"
        payload = {"version": uuid.uuid4().hex, "files": body.get("files", {})}
        validation_root = agents_root / ".validation"
        path = install_bundle(validation_root / "bundles", aid, payload)
        return await ProbeRunner(current(), client, validation_root).probe(
            path, mcp=bool(body.get("mcp"))
        )

    @application.post("/internal/v1/hooks/compile")
    async def compile_hook(body: dict):
        files = {
            relative_file(k): base64.b64decode(v, validate=True)
            for k, v in body.get("files", {}).items()
        }
        if len(files) > 1000 or sum(map(len, files.values())) > 100 * 1024**2:
            raise HTTPException(413, "Hook files exceed limit")
        result = await ProbeRunner(current(), client, agents_root / ".validation").compile_hook(
            {"files": files}
        )
        return {
            "files": {
                k: base64.b64encode(v).decode() for k, v in result["files"].items()
            }
        }

    return application


app = create_app()
if __name__ == "__main__":
    run("sandbox_manager")
