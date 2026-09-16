"""Durable cross-service jobs; no Docker or catalog database access."""

import asyncio, hashlib, json, os, time, uuid
from pathlib import Path
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, HTTPException, Query
from shared_libs.service import configure_service, settings, internal_client
from shared_libs.logging import TRACE_CONTEXT, emit
from .src.store import Store
from .src.recovery import Recovery, RecoveryPolicy
from .src.requests import (
    OperationRequest,
    ApplyRequest,
    DeleteRequest,
    SandboxRequest,
    parse,
)
from .src.load_tests import LoadTests
from .src.load_test_api import create_load_test_router


class Workflows:
    def __init__(self, store, config):
        self.store = store
        self.config = config
        self.lock = asyncio.Lock()
        self.tasks = set()
        self.clients = {
            name: internal_client(config, name) for name in config["services"]
        }

    async def call(self, service, path, payload=None, method=None):
        url = path
        try:
            result = await self.clients[service].request(
                method or ("POST" if payload is not None else "GET"),
                url,
                json=payload,
                timeout=180,
            )
            if result.is_error:
                raise HTTPException(
                    result.status_code,
                    result.json().get("detail", "Dependency rejected operation"),
                )
            return result.json()
        except httpx.HTTPError:
            raise HTTPException(503, service + " unavailable")

    def spawn(self, jid):
        task = asyncio.create_task(self.traced_run(jid))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def traced_run(self, jid):
        job = self.store.get(jid)
        context = {
            "trace_id": job.get("trace_id") or uuid.uuid4().hex,
            "span_id": uuid.uuid4().hex[:16],
            "parent_span_id": job.get("request_span_id"),
            "job_id": jid,
            "request_id": job.get("originating_request_id"),
        }
        token = TRACE_CONTEXT.set(context)
        emit(
            "job_started",
            module="operations",
            job_id=jid,
            agent_id=job.get("scope", job["target"]),
        )
        try:
            await self.run(jid)
        finally:
            result = self.store.get(jid)
            emit(
                "job_finished",
                module="operations",
                job_id=jid,
                error_code=result["status"]
                if result["status"] != "succeeded"
                else None,
            )
            TRACE_CONTEXT.reset(token)

    async def reconcile(self, jid, request_id):
        job = self.store.get(jid)
        if job["status"] == "succeeded":
            return {"job_id": jid, "status": "succeeded"}
        if job["status"] not in {"needs_recovery", "interrupted", "failed"}:
            raise HTTPException(409, "Job is not awaiting reconciliation")
        result = None
        if job.get("release_id"):
            release = await self.call(
                "catalog_service", "/internal/v1/releases/" + job["release_id"]
            )
            if not release.get("committed"):
                if job["kind"] == "models.apply":
                    observed = await self.call(
                        "model_gateway", "/internal/v1/config/status"
                    )
                    verified = (
                        observed.get("ready")
                        and observed.get("release_id") == release["release_id"]
                    )
                else:
                    observed = await self.call(
                        "sandbox_manager",
                        "/internal/v1/agents/" + job["target"] + "/application-status",
                    )
                    verified = observed.get("verified") and str(
                        observed.get("version")
                    ) == str(release["version"])
                if not verified:
                    raise HTTPException(
                        409,
                        "Applied version is not verified; inspect execution service before reconciliation",
                    )
                result = await self.call(
                    "catalog_service",
                    "/internal/v1/releases/" + release["release_id"] + "/commit",
                    {},
                )
            else:
                result = {"version": release["version"]}
            await self.call(
                "sandbox_manager",
                "/internal/v1/agents/" + job["target"] + "/actions",
                {"action": "resume", "request_id": request_id + ":resume"},
            )
        elif job["kind"].startswith("sandbox."):
            observed = await self.call(
                "sandbox_manager", "/internal/v1/sandboxes/" + job["target"]
            )
            desired = "destroyed" if job["kind"] == "sandbox.destroy" else "stopped" if job["kind"] == "sandbox.stop" else "ready"
            if observed.get("status") != desired:
                raise HTTPException(
                    409, "Observed sandbox does not match requested state"
                )
            if desired == "destroyed" and observed.get("container_id"):
                raise HTTPException(409, "Container removal has not been confirmed")
            if job["kind"] in {"sandbox.restart", "sandbox.recover"} and observed.get(
                "container_id"
            ) == job.get("before", {}).get("container_id"):
                raise HTTPException(
                    409, "A replacement container has not been observed"
                )
            self.store.state(
                "desired:" + job["target"],
                {"state": "on_demand" if desired == "destroyed" else "stopped" if desired == "stopped" else "running"},
            )
            result = {"sandbox_id": job["target"], "observed": desired}
        elif job["kind"] == "agent.delete":
            try:
                await self.call(
                    "catalog_service",
                    "/internal/v1/agents/" + job["target"] + "/deletion-impact",
                )
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
            else:
                raise HTTPException(
                    409,
                    "Agent deletion is incomplete; review remaining deletion impact",
                )
            sandbox = await self.call(
                "sandbox_manager",
                "/internal/v1/agents/" + job["target"] + "/deletion-impact",
            )
            files = await self.call(
                "file_service",
                "/internal/v1/agents/" + job["target"] + "/deletion-impact",
            )
            if (
                sandbox.get("sandboxes")
                or sandbox.get("sessions")
                or files.get("files")
            ):
                raise HTTPException(409, "Owned data remains after deletion")
            await self.call(
                "sandbox_manager",
                "/internal/v1/agents/" + job["target"] + "/actions",
                {"action": "resume", "request_id": request_id + ":resume"},
            )
            result = {"deleted": True}
        else:
            raise HTTPException(
                409, "No completed execution evidence exists for this job"
            )
        self.store.update(
            jid,
            status="succeeded",
            checkpoint="complete",
            result=result,
            reconciled=True,
        )
        emit(
            "job_reconciled",
            module="operations",
            job_id=jid,
            trace_id=job.get("trace_id"),
        )
        return {"job_id": jid, "status": "succeeded"}

    async def action(self, job, action, **extra):
        return await self.call(
            "sandbox_manager",
            "/internal/v1/agents/" + job["target"] + "/actions",
            {
                "action": action,
                "request_id": job.get("execution_id", job["id"]) + ":" + action,
                **extra,
            },
        )

    def checkpoint(self, jid, name, **values):
        if self.store.get(jid)["status"] == "cancelled":
            raise asyncio.CancelledError()
        try:
            self.store.transition(
                jid,
                {"queued", "running", "waiting", "applying"},
                checkpoint=name,
                **values,
            )
        except HTTPException:
            if self.store.get(jid)["status"] == "cancelled":
                raise asyncio.CancelledError()
            raise
        emit("job_checkpoint." + name, module="operations", job_id=jid)

    async def run(self, jid):
        job = self.store.get(jid)
        applied = False
        apply_started = False
        quiesce_started = False
        release = None
        previous = None
        compensated = False
        commit_started = False
        commit_state_known = False
        try:
            self.checkpoint(jid, "prepare", status="running")
            if job["kind"] in {"agent.apply", "models.apply"}:
                if job["kind"] == "agent.apply":
                    try:
                        previous = await self.call(
                            "catalog_service",
                            "/internal/v1/agents/" + job["target"] + "/bundle",
                        )
                    except HTTPException as exc:
                        if exc.status_code != 404:
                            raise
                if job.get("release_id"):
                    release = await self.call(
                        "catalog_service", "/internal/v1/releases/" + job["release_id"]
                    )
                else:
                    release = await self.call(
                        "catalog_service",
                        "/internal/v1/releases/prepare",
                        {
                            "kind": job["kind"],
                            "target": job["target"],
                            **job["payload"],
                        },
                    )
                self.checkpoint(jid, "validate", release_id=release["release_id"])
                if job["kind"] == "agent.apply":
                    await self.call(
                        "sandbox_manager",
                        "/internal/v1/probes",
                        {"files": release["files"], "mcp": False},
                    )
                else:
                    await self.call(
                        "model_gateway", "/internal/v1/config/validate", release
                    )
                self.checkpoint(jid, "quiesce", status="waiting")
                quiesce_started = True
                await self.action(job, "quiesce")
                self.checkpoint(jid, "apply", status="applying")
                apply_started = True
                if job["kind"] == "agent.apply":
                    await self.action(job, "apply", bundle=release)
                else:
                    await self.call(
                        "model_gateway", "/internal/v1/config/activate", release
                    )
                applied = True
                self.checkpoint(jid, "verify", apply_acknowledged=True)
                if job["kind"] == "agent.apply":
                    await self.action(job, "verify")
                else:
                    status = await self.call(
                        "model_gateway", "/internal/v1/config/status"
                    )
                    if status.get("release_id") != release[
                        "release_id"
                    ] or not status.get("ready"):
                        raise HTTPException(
                            503, "Applied model gateway version failed verification"
                        )
                self.checkpoint(jid, "commit")
                commit_started = True
                try:
                    result = await self.call(
                        "catalog_service",
                        "/internal/v1/releases/" + release["release_id"] + "/commit",
                        {},
                    )
                    commit_state_known = True
                except HTTPException:
                    state = await self.call(
                        "catalog_service",
                        "/internal/v1/releases/" + release["release_id"],
                    )
                    commit_state_known = True
                    if not state.get("committed"):
                        raise
                    result = {"version": state["version"]}
            elif job["kind"].startswith("sandbox."):
                self.checkpoint(jid, "apply", status="applying")
                apply_started = True
                action = job["kind"].split(".")[1]
                result = await self.call(
                    "sandbox_manager",
                    "/internal/v1/sandboxes/" + job["target"] + "/actions",
                    {
                        "action": action,
                        "request_id": job.get("execution_id", job["id"]),
                        **job["payload"],
                    },
                )
                applied = True
            else:
                action = job["kind"].split(".")[1]
                self.checkpoint(jid, "quiesce", status="waiting")
                quiesce_started = True
                await self.action(job, "quiesce")
                self.checkpoint(jid, "apply", status="applying")
                apply_started = True
                if action in {"delete", "delete-empty"}:
                    impacts = job["payload"].get("service_impacts", {})
                    if action in {"delete", "delete-empty"}:
                        await self.call(
                            "catalog_service",
                            "/internal/v1/agents/" + job["target"] + "/lifecycle",
                            {
                                "action": "deleting",
                                "request_id": job.get("execution_id", job["id"]),
                                "expected_fingerprint": impacts.get("catalog", {}).get(
                                    "fingerprint"
                                ),
                            },
                        )
                    await self.action(
                        job,
                        "delete",
                        empty_only=action == "delete-empty",
                        expected_fingerprint=impacts.get("sandbox", {}).get(
                            "fingerprint"
                        ),
                    )
                    self.store.update(
                        jid, checkpoint="cleanup-files", sandbox_deleted=True
                    )
                    await self.call(
                        "file_service",
                        "/internal/v1/agents/" + job["target"] + "/cleanup",
                        {
                            "request_id": job.get("execution_id", job["id"]),
                            "expected_fingerprint": impacts.get("files", {}).get(
                                "fingerprint"
                            ),
                            "empty_only": action == "delete-empty",
                        },
                    )
                    self.store.update(
                        jid, checkpoint="cleanup-catalog", files_deleted=True
                    )
                    action = "delete"
                elif action == "archive":
                    await self.action(job, "archive")
                result = await self.call(
                    "catalog_service",
                    "/internal/v1/agents/" + job["target"] + "/lifecycle",
                    {
                        "action": action,
                        "request_id": job.get("execution_id", job["id"]),
                        "expected_fingerprint": job["payload"]
                        .get("service_impacts", {})
                        .get("catalog", {})
                        .get("fingerprint"),
                    },
                )
                applied = True
            if job["kind"] in {"sandbox.stop", "sandbox.start", "sandbox.restart", "sandbox.destroy"}:
                self.store.state(
                    "desired:" + job["target"],
                    {
                        "state": "on_demand" if job["kind"] == "sandbox.destroy" else "stopped"
                        if job["kind"] == "sandbox.stop"
                        else "running"
                    },
                )
            self.store.update(
                jid, status="succeeded", checkpoint="complete", result=result
            )
        except asyncio.CancelledError:
            if self.store.get(jid)["status"] != "cancelled":
                self.store.update(
                    jid,
                    status="needs_recovery" if apply_started else "interrupted",
                    error="Worker stopped; inspect checkpoint before retry",
                )
        except Exception as exc:
            # Only compensate an acknowledged application. An uncertain network
            # result is held for inspection, never blindly replayed.
            if applied and release and (not commit_started or commit_state_known):
                try:
                    if job["kind"] == "models.apply":
                        await self.call(
                            "model_gateway",
                            "/internal/v1/config/rollback",
                            {"release_id": release["release_id"]},
                        )
                        compensated = True
                    elif previous:
                        await self.call(
                            "sandbox_manager",
                            "/internal/v1/agents/" + job["target"] + "/actions",
                            {
                                "action": "apply",
                                "request_id": job["id"] + ":compensate",
                                "bundle": previous,
                            },
                        )
                        await self.call(
                            "sandbox_manager",
                            "/internal/v1/agents/" + job["target"] + "/actions",
                            {
                                "action": "verify",
                                "request_id": job["id"] + ":compensate:verify",
                            },
                        )
                        compensated = True
                except Exception:
                    pass
            self.store.update(
                jid,
                status="needs_recovery"
                if apply_started and not compensated
                else "failed",
                error=exc.detail
                if isinstance(exc, HTTPException)
                else "Operation failed",
                applied=applied,
                compensated=compensated,
            )
        finally:
            # An uncertain destructive outcome keeps its persistent admission
            # lease until an operator resolves the checkpoint.
            if quiesce_started and self.store.get(jid)["status"] != "needs_recovery":
                try:
                    await self.action(job, "resume")
                except Exception:
                    self.store.update(
                        jid,
                        status="needs_recovery",
                        error="Unable to release target admission block",
                    )


def create_app(data_root=None):
    config = settings("operations")
    store = Store(Path(data_root or config["data_root"]))
    runtime = Workflows(store, config)
    load = LoadTests(runtime)

    def load_client():
        client = internal_client(config, "sandbox_manager")
        client.timeout = httpx.Timeout(None)
        return client

    load.api_factory = load_client
    runtime.load_tests = load
    recovery = Recovery(runtime)

    @asynccontextmanager
    async def lifespan(app):
        load.store.recover()
        for job in store.jobs():
            if job["status"] in {"running", "waiting", "applying"}:
                store.update(
                    job["id"],
                    status="needs_recovery",
                    error="Service restarted; inspect checkpoint before retry",
                )
                emit(
                    "job_interrupted",
                    module="operations",
                    job_id=job["id"],
                    trace_id=job.get("trace_id"),
                    span_id=uuid.uuid4().hex[:16],
                    parent_span_id=job.get("request_span_id"),
                    error_code="SERVICE_RESTARTED",
                )
            elif job["status"] == "queued":
                runtime.spawn(job["id"])
        recovery_task = asyncio.create_task(recovery.loop())
        yield
        recovery_task.cancel()
        await asyncio.gather(recovery_task, return_exceptions=True)
        for task in runtime.tasks:
            task.cancel()
        await asyncio.gather(*runtime.tasks, return_exceptions=True)
        await asyncio.gather(*(c.aclose() for c in runtime.clients.values()))

    app = FastAPI(title="operations", version="1.0.0", lifespan=lifespan)
    configure_service(app, "operations", config)
    app.state.store = store
    app.state.runtime = runtime
    app.include_router(create_load_test_router(load))

    async def deletion_impact(aid):
        catalog, sandbox, files = await asyncio.gather(
            runtime.call(
                "catalog_service", "/internal/v1/agents/" + aid + "/deletion-impact"
            ),
            runtime.call(
                "sandbox_manager", "/internal/v1/agents/" + aid + "/deletion-impact"
            ),
            runtime.call(
                "file_service", "/internal/v1/agents/" + aid + "/deletion-impact"
            ),
        )
        impacts = {"catalog": catalog, "sandbox": sandbox, "files": files}
        fingerprint = hashlib.sha256(
            json.dumps(impacts, sort_keys=True).encode()
        ).hexdigest()
        return {
            **catalog,
            "sandboxes": sandbox.get("sandboxes", []),
            "sessions": sandbox.get("sessions", 0),
            "files": files.get("files", 0),
            "bytes": files.get("bytes", 0),
            "fingerprint": fingerprint,
            "service_impacts": impacts,
            "warning": "Permanently deletes Agent configuration history, sessions, workspace and private resources. Global resources are retained.",
        }

    async def submit(kind, target, payload):
        payload = dict(payload)
        for existing in store.jobs():
            if (
                payload.get("request_id")
                and existing["request_id"] == payload["request_id"]
            ):
                original = existing.get(
                    "original_input",
                    existing["payload"].get("_input", existing["payload"]),
                )
                if (
                    existing["kind"] != kind
                    or existing["target"] != target
                    or original != payload
                ):
                    raise HTTPException(
                        409, "Request ID already used with different operation"
                    )
                return {"job_id": existing["id"]}
        original = dict(payload)
        if kind.startswith("sandbox.") and payload.get("force_preview_id"):
            preview = store.state("force:" + payload["force_preview_id"])
            if (
                not preview
                or preview["sandbox_id"] != target
                or preview["expires"] < time.time()
                or payload.get("confirmation") != target
            ):
                raise HTTPException(
                    409,
                    "Force operation needs a current preview and exact sandbox ID confirmation",
                )
            payload.update(
                force=True, preview_id=payload["force_preview_id"], _input=original
            )
        if kind == "agent.delete":
            preview = store.state("preview:" + payload.get("preview_id", ""))
            if (
                not preview
                or preview["agent_id"] != target
                or preview["expires"] < time.time()
                or payload.get("confirmation") != target
            ):
                raise HTTPException(
                    409,
                    "Fresh deletion preview and exact Agent ID confirmation required",
                )
            current = await deletion_impact(target)
            if current["fingerprint"] != preview["fingerprint"]:
                raise HTTPException(409, "Deletion impact changed; preview again")
            if current["lifecycle"] not in {"archived", "deleting"}:
                raise HTTPException(409, "Archive the Agent before permanent deletion")
            payload.update(service_impacts=current["service_impacts"], _input=original)
        elif kind == "agent.delete-empty":
            current = await deletion_impact(target)
            if current["sandboxes"] or current["sessions"] or current["files"]:
                raise HTTPException(
                    409, "Agent has runtime data; archive and use permanent deletion"
                )
            payload.update(service_impacts=current["service_impacts"], _input=original)
        before = (
            await runtime.call("sandbox_manager", "/internal/v1/sandboxes/" + target)
            if kind.startswith("sandbox.")
            else None
        )
        scope = before["agent_id"] if before else target
        if kind not in {"agent.apply", "models.apply"}:
            await runtime.call(
                "catalog_service",
                "/internal/v1/agents/" + scope + "/operation-check",
                {"kind": kind, "revision": payload.get("revision")},
            )
        job, created = store.submit(kind, target, payload, scope=scope)
        if created:
            if before:
                store.update(
                    job["id"],
                    before={
                        k: before.get(k)
                        for k in ("container_id", "activity_generation", "status")
                    },
                )
            runtime.spawn(job["id"])
        return {"job_id": job["id"]}

    @app.get("/internal/v1/file-admission")
    def file_admission(agent_id: str, username: str, write: bool = False):
        pending = [
            j
            for j in store.jobs()
            if j.get("scope", j["target"]) == agent_id
            and j["kind"].startswith("agent.delete")
            and j["status"]
            in {
                "queued",
                "running",
                "waiting",
                "applying",
                "needs_recovery",
                "interrupted",
            }
        ]
        if pending:
            raise HTTPException(409, "Agent deletion pending")
        if username.startswith("loadtest-"):
            user = load.store.user(agent_id, username)
            if not user or user["storage_state"] != "retained":
                raise HTTPException(
                    409, "Load-test storage unavailable or being cleaned up"
                )
            return {
                "allowed": True,
                "resources": {
                    "load_test": user["run_id"],
                    "cpu": user["cpu_limit"],
                    "memory_mb": user["memory_mb"],
                    "pids": 256,
                },
            }
        return {"allowed": True, "resources": None}

    @app.get("/internal/v1/cleanup-authorization")
    def cleanup_authorization(
        agent_id: str,
        request_id: str,
        username: str | None = None,
        run_id: str | None = None,
    ):
        if run_id and username:
            report = load.store.get(run_id)
            user = load.store.user(agent_id, username)
            if (
                report["cleanup_status"] == "cleaning"
                and user
                and user["run_id"] == run_id
                and user["storage_state"] == "cleaning"
                and request_id == run_id + ":" + username
            ):
                return {"allowed": True}
        else:
            for job in store.jobs():
                if (
                    job["target"] == agent_id
                    and job["kind"] in {"agent.delete", "agent.delete-empty"}
                    and job.get("execution_id", job["id"]) == request_id
                    and job["status"] == "applying"
                ):
                    return {"allowed": True}
        raise HTTPException(409, "No matching active cleanup intent")

    @app.get("/internal/v1/sandboxes/{sid}/desired-state")
    def desired_state(sid: str):
        return store.state("desired:" + sid) or {"state": "running"}

    @app.get("/internal/v1/admission")
    def admission(agent_id: str, username: str):
        active = [
            j
            for j in store.jobs()
            if j.get("scope", j["target"]) in {agent_id, "*"}
            and j["status"]
            in {
                "queued",
                "running",
                "waiting",
                "applying",
                "needs_recovery",
                "interrupted",
            }
        ]
        if any(j["status"] in {"needs_recovery", "interrupted"} for j in active):
            raise HTTPException(
                409, "An interrupted operation requires reconciliation before execution"
            )
        if any(j["kind"].startswith(("agent.delete", "agent.archive")) for j in active):
            raise HTTPException(409, "Agent lifecycle operation pending")
        sid = (
            "sbx_"
            + hashlib.sha256((agent_id + "\x00" + username).encode()).hexdigest()[:20]
        )
        if store.state("desired:" + sid) == {"state": "stopped"} and not any(
            j["target"] == sid and j["kind"] in {"sandbox.start", "sandbox.restart"}
            for j in active
        ):
            raise HTTPException(
                409, "Sandbox was stopped manually; start it in sandbox management"
            )
        user = load.resources_for(agent_id, username)
        return {
            "allowed": True,
            "resources": {
                "cpu": user["cpu_limit"],
                "memory_mb": user["memory_mb"],
                "pids": 256,
                "load_test": user["run_id"],
            }
            if user
            else None,
        }

    @app.get("/health/ready")
    async def ready():
        for name in (
            "catalog_service",
            "sandbox_manager",
            "file_service",
            "model_gateway",
        ):
            await runtime.call(name, "/health/live")
        return {"ready": True, "module": "operations"}

    def public_job(job):
        return {
            **{k: v for k, v in job.items() if k not in {"payload", "original_input"}},
            "target": job.get("scope", job["target"]),
            "resource_id": job["target"],
        }

    @app.get("/cloud/admin/jobs")
    def jobs(
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=100),
        target: str | None = None,
    ):
        values = sorted(
            [
                j
                for j in store.jobs()
                if not target or j["target"] == target or j.get("scope") == target
            ],
            key=lambda j: j["created"],
            reverse=True,
        )
        return {
            "total": len(values),
            "items": [public_job(j) for j in values[offset : offset + limit]],
        }

    @app.get("/cloud/admin/jobs/export")
    def export_jobs():
        from starlette.responses import Response
        records = sorted((public_job(j) for j in store.jobs()), key=lambda j: j["created"], reverse=True)
        return Response(json.dumps(records, ensure_ascii=False), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="operation-history.json"'})

    @app.get("/cloud/admin/jobs/{jid}")
    def job(jid: str):
        return public_job(store.get(jid))

    @app.post("/cloud/admin/jobs/{jid}/retry")
    async def retry_deletion(jid: str, payload: DeleteRequest):
        job = store.get(jid)
        aid = job["target"]
        body = payload.model_dump(exclude_unset=True)
        if job.get("retry_request_id") == payload.request_id:
            if job["payload"].get("_input") != body:
                raise HTTPException(
                    409, "Retry request ID reused with different parameters"
                )
            return {"job_id": jid}
        preview = store.state("preview:" + payload.preview_id)
        if (
            not preview
            or preview["agent_id"] != aid
            or preview["expires"] < time.time()
            or payload.confirmation != aid
        ):
            raise HTTPException(
                409,
                "Retry needs a fresh deletion preview and exact Agent ID confirmation",
            )
        impact = await deletion_impact(aid)
        if impact["fingerprint"] != preview["fingerprint"] or impact[
            "lifecycle"
        ] not in {"archived", "deleting"}:
            raise HTTPException(
                409, "Deletion impact changed; preview remaining data again"
            )
        _, created = store.retry_deletion(
            jid, {**body, "service_impacts": impact["service_impacts"], "_input": body}
        )
        if created:
            runtime.spawn(jid)
        return {"job_id": jid}

    @app.post("/cloud/admin/jobs/{jid}/reconcile")
    async def reconcile_job(jid: str, payload: OperationRequest):
        return await runtime.reconcile(jid, payload.request_id)

    @app.post("/cloud/admin/jobs/{jid}/cancel")
    def cancel(jid: str):
        j = store.get(jid)
        if (
            j["status"] not in {"queued", "running", "waiting", "cancelled"}
            or j["kind"] == "agent.delete"
        ):
            raise HTTPException(409, "Job cannot be cancelled at this checkpoint")
        return store.transition(
            jid, {"queued", "running", "waiting", "cancelled"}, status="cancelled"
        )

    @app.post("/cloud/admin/models/apply")
    async def apply_models(payload: ApplyRequest = ApplyRequest()):
        return await submit("models.apply", "*", payload.model_dump(exclude_unset=True))

    @app.post("/cloud/admin/agents/{aid}/apply")
    @app.post("/cloud/admin/agents/{aid}/rollback")
    async def apply_agent(aid: str, payload: ApplyRequest = ApplyRequest()):
        return await submit("agent.apply", aid, payload.model_dump(exclude_unset=True))

    @app.get("/cloud/admin/sandboxes")
    async def sandboxes(
        q: str = "",
        status: str | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ):
        from urllib.parse import urlencode

        result = await runtime.call(
            "sandbox_manager",
            "/internal/v1/sandboxes?"
            + urlencode(
                {"offset": offset, "limit": limit, "q": q, "status": status or ""}
            ),
        )
        for row in result["items"]:
            sid = row["sandbox_id"]
            jobs = [j for j in store.jobs() if j["target"] == sid]
            row.update(
                recovery=recovery.state(sid),
                desired_state=(store.state("desired:" + sid) or {}).get(
                    "state", "running"
                ),
                last_operation=max(jobs, key=lambda j: j["created"])["id"]
                if jobs
                else None,
            )
        return {
            **result,
            "offset": offset,
            "limit": limit,
            "sampled_at": time.time(),
            "status_source": "registry_health_monitor",
        }

    @app.get("/cloud/admin/sandboxes/{sid}")
    async def detail(sid: str):
        value = await runtime.call("sandbox_manager", "/internal/v1/sandboxes/" + sid)
        return {
            **value,
            "recovery": recovery.state(sid),
            "operations": sorted(
                [public_job(j) for j in store.jobs() if j["target"] == sid],
                key=lambda j: j["created"],
                reverse=True,
            )[:20],
        }

    @app.get("/cloud/admin/sandboxes/{sid}/force-preview")
    async def force(sid: str):
        preview = await runtime.call(
            "sandbox_manager", "/internal/v1/sandboxes/" + sid + "/force-preview"
        )
        store.state("force:" + preview["preview_id"], preview)
        return {
            **preview,
            "sessions": [
                s.get("session_id") if isinstance(s, dict) else s
                for s in preview.get("sessions", [])
            ],
        }

    @app.post("/cloud/admin/sandboxes/{sid}/{action}")
    async def sandbox_action(sid: str, action: str, payload: dict):
        if action not in {"start", "stop", "restart", "destroy"}:
            raise HTTPException(404, "Unknown operation")
        return await submit(
            "sandbox." + action,
            sid,
            parse(OperationRequest if action == "start" else SandboxRequest, payload),
        )

    @app.get("/cloud/admin/agents/{aid}/delete-preview")
    async def delete_preview(aid: str):
        impact = await deletion_impact(aid)
        pid = "delete_" + uuid.uuid4().hex
        preview = {"preview_id": pid, "expires": time.time() + 300, **impact}
        store.state("preview:" + pid, preview)
        return {k: v for k, v in preview.items() if k != "service_impacts"}

    @app.post("/cloud/admin/agents/{aid}/{action}")
    async def agent_action(aid: str, action: str, payload: dict):
        if action not in {"archive", "restore", "delete", "delete-empty"}:
            raise HTTPException(404, "Unknown operation")
        return await submit(
            "agent." + action,
            aid,
            parse(DeleteRequest if action == "delete" else OperationRequest, payload),
        )

    @app.get("/cloud/admin/recovery-policy")
    def policy():
        return recovery.policy()

    @app.put("/cloud/admin/recovery-policy")
    def save_policy(payload: RecoveryPolicy):
        return store.state("recovery-policy", payload.model_dump())

    @app.get("/cloud/operations/security-status")
    async def security():
        services = {}
        for service in (
            "catalog_service",
            "sandbox_manager",
            "file_service",
            "model_gateway",
            "observability",
        ):
            try:
                services[service] = await runtime.call(service, "/health/ready")
            except HTTPException as exc:
                services[service] = {"ready": False, "error": exc.detail}
        try:
            runtime_security = await runtime.call(
                "sandbox_manager", "/internal/v1/runtime-security"
            )
        except HTTPException as exc:
            runtime_security = {
                "scope": "managed_sandboxes",
                "status": "unknown",
                "error": exc.detail,
            }
        return {
            "scope": "managed_sandboxes",
            "internal_authentication_configured": bool(config.get("service_token")),
            "runtime_security": runtime_security,
            "services": services,
            "failed_operations": [
                j["id"]
                for j in store.jobs()
                if j["status"] in {"failed", "needs_recovery"}
            ],
        }

    return app


app = create_app()

if __name__ == "__main__":
    from shared_libs.service import run

    run("operations")
