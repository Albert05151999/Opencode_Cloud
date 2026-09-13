"""File-owned admission locks and durable cleanup receipts."""

import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import HTTPException
from shared_libs.service import internal_client
from shared_libs.workspace_paths import validate_identifier


class FileCoordination:
    def __init__(self, config, client=None):
        self.config = config
        self.locks = {}
        root = Path(config["data_root"])
        root.mkdir(parents=True, exist_ok=True)
        self.journal = root / "cleanup.db"
        with sqlite3.connect(self.journal) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS cleanups(request_id TEXT PRIMARY KEY, payload TEXT NOT NULL, result TEXT)"
            )
        self._owns_client = client is None
        self.client = client or internal_client(config, "operations")

    async def check(self, path, **params):
        try:
            response = await self.client.get(
                path, params={k: v for k, v in params.items() if v is not None}
            )
            if response.is_error:
                raise HTTPException(
                    response.status_code, "File operation is not admitted by operations"
                )
            result = response.json()
            if not result.get("allowed"):
                raise HTTPException(409, "File operation is not admitted")
            return result
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, "Operations admission unavailable") from exc

    async def aclose(self):
        if self._owns_client:
            await self.client.aclose()

    @asynccontextmanager
    async def guard(self, agent_id):
        validate_identifier(agent_id, "agent_id")
        async with self.locks.setdefault(agent_id, asyncio.Lock()):
            yield

    async def admission(self, agent_id, username, upload=False):
        validate_identifier(username, "username")
        result = await self.check(
            "/internal/v1/file-admission",
            agent_id=agent_id,
            username=username,
            write=True,
        )
        if upload and (result.get("resources") or {}).get("load_test"):
            raise HTTPException(
                409,
                "Load-test users only accept the fixed workload, not manual uploads",
            )

    def replay(self, request_id, payload):
        if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
            raise HTTPException(422, "Cleanup requires a bounded request_id")
        canonical = json.dumps(payload, sort_keys=True)
        with sqlite3.connect(self.journal) as db:
            row = db.execute(
                "SELECT payload,result FROM cleanups WHERE request_id=?", (request_id,)
            ).fetchone()
        if row:
            if row[0] != canonical:
                raise HTTPException(
                    409, "Cleanup request_id was reused with different parameters"
                )
            if row[1] is None:
                raise HTTPException(
                    409,
                    "Cleanup was interrupted; reconcile its result before continuing",
                )
            return json.loads(row[1])
        return None

    def begin(self, request_id, payload):
        try:
            with sqlite3.connect(self.journal) as db:
                db.execute(
                    "INSERT INTO cleanups VALUES(?,?,NULL)",
                    (request_id, json.dumps(payload, sort_keys=True)),
                )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "Cleanup already started") from exc

    def finish(self, request_id, result):
        with sqlite3.connect(self.journal) as db:
            db.execute(
                "UPDATE cleanups SET result=? WHERE request_id=?",
                (json.dumps(result), request_id),
            )
