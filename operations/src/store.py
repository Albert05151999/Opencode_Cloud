"""Single-writer operations state with persistent idempotency and target leases."""

import json, sqlite3, time, uuid, threading
from pathlib import Path
from contextlib import contextmanager
from fastapi import HTTPException
from shared_libs.logging import TRACE_CONTEXT, emit


class Store:
    def __init__(self, root):
        self.lock = threading.RLock()
        Path(root).mkdir(parents=True, exist_ok=True)
        self.path = Path(root) / "operations.db"
        with self.connect() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, request_id TEXT UNIQUE, target TEXT, document TEXT); CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, document TEXT);"
            )

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def jobs(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT document FROM jobs")]

    def get(self, jid):
        with self.connect() as db:
            row = db.execute("SELECT document FROM jobs WHERE id=?", (jid,)).fetchone()
        if not row:
            raise HTTPException(404, "Job not found")
        return json.loads(row[0])

    def update(self, jid, **changes):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT document FROM jobs WHERE id=?", (jid,)).fetchone()
            job = json.loads(row[0])
            job.update(changes, updated=time.time())
            db.execute("UPDATE jobs SET document=? WHERE id=?", (json.dumps(job), jid))
        return job

    def submit(self, kind, target, payload, scope=None):
        scope = scope or target
        request_id = payload.get("request_id") or uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT document FROM jobs WHERE request_id=?", (request_id,)
            ).fetchone()
            if row:
                job = json.loads(row[0])
                if (
                    job["kind"] != kind
                    or job["target"] != target
                    or job["payload"] != payload
                ):
                    raise HTTPException(
                        409, "Request ID already used with different operation"
                    )
                return job, False
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='load_tests'"
            ).fetchone():
                if scope == "*":
                    active_load = db.execute(
                        "SELECT 1 FROM load_tests WHERE status IN ('queued','preparing','running','cancelling') LIMIT 1"
                    ).fetchone()
                else:
                    active_load = db.execute(
                        "SELECT 1 FROM load_tests r JOIN load_test_users u ON u.run_id=r.id WHERE u.agent_id=? AND (r.status IN ('queued','preparing','running','cancelling') OR u.state='cleaning') LIMIT 1",
                        (scope,),
                    ).fetchone()
                if active_load:
                    raise HTTPException(409, "A load test pins this Agent version")
            active = [json.loads(r[0]) for r in db.execute("SELECT document FROM jobs")]
            if any(
                j["status"]
                in {
                    "queued",
                    "running",
                    "waiting",
                    "applying",
                    "needs_recovery",
                    "interrupted",
                }
                and (scope == "*" or j.get("scope", j["target"]) in {scope, "*"})
                for j in active
            ):
                raise HTTPException(409, "An operation already holds this target")
            job = {
                "id": uuid.uuid4().hex,
                "kind": kind,
                "target": target,
                "scope": scope,
                "payload": payload,
                "request_id": request_id,
                "status": "queued",
                "checkpoint": "prepare",
                "created": time.time(),
                "updated": time.time(),
            }
            trace = TRACE_CONTEXT.get()
            job["original_input"] = payload.get("_input", payload)
            job.update(
                trace_id=trace.get("trace_id") or uuid.uuid4().hex,
                request_span_id=trace.get("span_id"),
                originating_request_id=trace.get("request_id"),
            )
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?,?)",
                (job["id"], request_id, target, json.dumps(job)),
            )
        emit(
            "job_submitted",
            module="operations",
            job_id=job["id"],
            agent_id=scope,
            trace_id=job["trace_id"],
        )
        return job, True

    def retry_deletion(self, jid, payload):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT document FROM jobs WHERE id=?", (jid,)).fetchone()
            if not row:
                raise HTTPException(404, "Job not found")
            job = json.loads(row[0])
            if job.get("retry_request_id") == payload["request_id"]:
                if job["payload"] != payload:
                    raise HTTPException(
                        409, "Retry request ID reused with different impact"
                    )
                return job, False
            if job["kind"] != "agent.delete" or job["status"] not in {
                "failed",
                "needs_recovery",
                "interrupted",
            }:
                raise HTTPException(
                    409,
                    "Only interrupted permanent deletion accepts a newly confirmed retry",
                )
            for row in db.execute("SELECT document FROM jobs WHERE id != ?", (jid,)):
                other = json.loads(row[0])
                if other["status"] in {
                    "queued",
                    "running",
                    "waiting",
                    "applying",
                    "needs_recovery",
                    "interrupted",
                } and other.get("scope", other["target"]) in {
                    job.get("scope", job["target"]),
                    "*",
                }:
                    raise HTTPException(409, "Another operation holds this Agent")
            job.setdefault("attempts", []).append(
                {
                    k: job.get(k)
                    for k in (
                        "status",
                        "checkpoint",
                        "error",
                        "execution_id",
                        "updated",
                    )
                }
            )
            job.update(
                payload=payload,
                retry_request_id=payload["request_id"],
                execution_id=uuid.uuid4().hex,
                status="queued",
                checkpoint="prepare",
                error=None,
                updated=time.time(),
            )
            db.execute("UPDATE jobs SET document=? WHERE id=?", (json.dumps(job), jid))
        return job, True

    def transition(self, jid, allowed, **changes):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT document FROM jobs WHERE id=?", (jid,)).fetchone()
            if not row:
                raise HTTPException(404, "Job not found")
            job = json.loads(row[0])
            if job["status"] not in allowed:
                raise HTTPException(409, "Job state changed")
            job.update(changes, updated=time.time())
            db.execute("UPDATE jobs SET document=? WHERE id=?", (json.dumps(job), jid))
        return job

    def state(self, key, value=None):
        with self.connect() as db:
            if value is not None:
                db.execute(
                    "INSERT OR REPLACE INTO state VALUES (?,?)",
                    (key, json.dumps(value)),
                )
            row = db.execute(
                "SELECT document FROM state WHERE key=?", (key,)
            ).fetchone()
        return json.loads(row[0]) if row else None
