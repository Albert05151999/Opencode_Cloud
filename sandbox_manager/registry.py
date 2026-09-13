"""Single-host SQLite routing registry."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
from typing import Iterable, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SandboxRecord:
    sandbox_id: str
    agent_id: str
    username: str
    container_id: str | None
    host_port: int | None
    status: str
    image_version: str
    last_active_at: str
    created_at: str


@dataclass(frozen=True)
class SessionRoute:
    session_id: str
    sandbox_id: str
    agent_id: str
    username: str
    workspace_relpath: str
    created_at: str
    last_active_at: str


class Registry:
    def __init__(
        self,
        path: str | Path,
        migration_path: str | Path | None = None,
        *,
        synchronous: str = "FULL",
    ) -> None:
        if synchronous not in {"NORMAL", "FULL"}:
            raise ValueError("SQLite synchronous must be NORMAL or FULL")
        self.synchronous = synchronous
        self._writer_lock = threading.Lock()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migration_path = Path(
            migration_path
            or Path(__file__).resolve().parent / "migrations/001_initial.sql"
        )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
            connection.execute(f"PRAGMA synchronous = {self.synchronous}")
            with connection:
                yield connection
        finally:
            connection.close()

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        # Queue in-process writes before SQLite's busy backoff. Readers remain
        # independent; SQLite still arbitrates writers from other processes.
        with self._writer_lock:
            with self.connect() as connection:
                yield connection

    def initialize(self) -> None:
        sql = self.migration_path.read_text(encoding="utf-8")
        with self._write_connection() as connection:
            mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if mode.lower() != "wal":
                raise RuntimeError(f"Unable to enable SQLite WAL mode: {mode}")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                connection.executescript(sql)
            elif version != 1:
                raise RuntimeError(f"Unsupported registry schema version: {version}")

    @contextmanager
    def lifetime(self) -> Iterator[None]:
        """Keep WAL open across requests without holding a read transaction.

        Closing the last SQLite connection checkpoints and removes the WAL.
        A process-lifetime idle connection avoids repeating that work for each
        burst. Normal transaction connections still commit and close promptly.
        """
        with self.connect() as connection:
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
            yield

    def upsert_agent(
        self, agent_id: str, config_path: str, image: str, enabled: bool = True
    ) -> None:
        # Even an ON CONFLICT no-op takes SQLite's writer lock. Avoid that
        # contention on the common unchanged-config acquire path.
        with self.connect() as connection:
            current = connection.execute(
                "SELECT config_path, image, enabled FROM agents WHERE agent_id=?",
                (agent_id,),
            ).fetchone()
        if current is not None and tuple(current) == (config_path, image, int(enabled)):
            return
        with self._write_connection() as connection:
            connection.execute(
                """INSERT INTO agents(agent_id, config_path, image, enabled, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(agent_id) DO UPDATE SET
                     config_path=excluded.config_path, image=excluded.image,
                     enabled=excluded.enabled, updated_at=excluded.updated_at
                   WHERE agents.config_path IS NOT excluded.config_path
                      OR agents.image IS NOT excluded.image
                      OR agents.enabled IS NOT excluded.enabled""",
                (agent_id, config_path, image, int(enabled), utc_now()),
            )

    @staticmethod
    def _sandbox(row: sqlite3.Row | None) -> SandboxRecord | None:
        return SandboxRecord(**dict(row)) if row else None

    @staticmethod
    def _session(row: sqlite3.Row | None) -> SessionRoute | None:
        return SessionRoute(**dict(row)) if row else None

    def get_sandbox(self, agent_id: str, username: str) -> SandboxRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sandboxes WHERE agent_id=? AND username=?",
                (agent_id, username),
            ).fetchone()
        return self._sandbox(row)

    def upsert_sandbox(
        self,
        *,
        sandbox_id: str,
        agent_id: str,
        username: str,
        container_id: str | None,
        host_port: int | None,
        status: str,
        image_version: str,
        last_active_at: str | None = None,
    ) -> SandboxRecord:
        now = last_active_at or utc_now()
        with self._write_connection() as connection:
            row = connection.execute(
                """INSERT INTO sandboxes(
                     sandbox_id, agent_id, username, container_id, host_port, status,
                     image_version, last_active_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(agent_id, username) DO UPDATE SET
                     container_id=excluded.container_id, host_port=excluded.host_port,
                     status=excluded.status, image_version=excluded.image_version,
                     last_active_at=excluded.last_active_at
                   RETURNING *""",
                (
                    sandbox_id,
                    agent_id,
                    username,
                    container_id,
                    host_port,
                    status,
                    image_version,
                    now,
                    now,
                ),
            ).fetchone()
        record = self._sandbox(row)
        assert record is not None
        return record

    def mark_sandbox_status(self, sandbox_id: str, status: str) -> bool:
        with self._write_connection() as connection:
            cursor = connection.execute(
                "UPDATE sandboxes SET status=?, last_active_at=? WHERE sandbox_id=?",
                (status, utc_now(), sandbox_id),
            )
        return cursor.rowcount == 1

    def list_sandboxes(self) -> list[SandboxRecord]:
        with self.connect() as connection:
            return [
                SandboxRecord(**dict(row))
                for row in connection.execute("SELECT * FROM sandboxes")
            ]

    def touch_sandbox(self, sandbox_id: str) -> None:
        with self._write_connection() as connection:
            # Activity is a recovery hint, not a routing/ownership transaction.
            # WAL NORMAL survives process restarts; a host power loss may lose
            # the latest idle timestamp. Other writes keep FULL durability.
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute(
                "UPDATE sandboxes SET last_active_at=? WHERE sandbox_id=?",
                (utc_now(), sandbox_id),
            )

    def set_health_status(self, sandbox_id: str, status: str) -> None:
        """Health observation must not reset the idle clock."""
        with self._write_connection() as connection:
            connection.execute(
                "UPDATE sandboxes SET status=? WHERE sandbox_id=?", (status, sandbox_id)
            )

    def record_session(
        self,
        session_id: str,
        sandbox_id: str,
        agent_id: str,
        username: str,
        workspace_relpath: str,
    ) -> SessionRoute:
        result = self.record_sessions_batch(
            [(session_id, sandbox_id, agent_id, username, workspace_relpath)]
        )[0]
        if isinstance(result, Exception):
            raise result
        return result

    def record_sessions_batch(
        self,
        entries: list[tuple[str, str, str, str, str]],
    ) -> list[SessionRoute | Exception]:
        results: list[SessionRoute | Exception] = []
        with self._write_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for index, (
                session_id,
                sandbox_id,
                agent_id,
                username,
                workspace_relpath,
            ) in enumerate(entries):
                savepoint = f"session_entry_{index}"
                connection.execute(f"SAVEPOINT {savepoint}")
                try:
                    owner = connection.execute(
                        "SELECT agent_id, username FROM sandboxes WHERE sandbox_id=?",
                        (sandbox_id,),
                    ).fetchone()
                    if owner is None:
                        raise KeyError(f"Unknown sandbox: {sandbox_id}")
                    if (owner["agent_id"], owner["username"]) != (agent_id, username):
                        raise ValueError("Session route does not match sandbox owner")
                    now = utc_now()
                    row = connection.execute(
                        """INSERT INTO sessions(
                             session_id, sandbox_id, agent_id, username, workspace_relpath,
                             created_at, last_active_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(session_id) DO UPDATE SET
                             last_active_at=excluded.last_active_at
                           RETURNING *""",
                        (
                            session_id,
                            sandbox_id,
                            agent_id,
                            username,
                            workspace_relpath,
                            now,
                            now,
                        ),
                    ).fetchone()
                    route = self._session(row)
                    assert route is not None
                    if (
                        route.sandbox_id,
                        route.agent_id,
                        route.username,
                        route.workspace_relpath,
                    ) != (sandbox_id, agent_id, username, workspace_relpath):
                        raise ValueError("Session ID is already bound to another route")
                    connection.execute(
                        "UPDATE sandboxes SET last_active_at=? WHERE sandbox_id=?",
                        (utc_now(), sandbox_id),
                    )
                except (KeyError, ValueError) as error:
                    connection.execute(f"ROLLBACK TO {savepoint}")
                    connection.execute(f"RELEASE {savepoint}")
                    results.append(error)
                else:
                    connection.execute(f"RELEASE {savepoint}")
                    results.append(route)
        return results

    def get_session_route(self, session_id: str) -> SessionRoute | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        return self._session(row)

    def list_sessions_for_sandbox(self, sandbox_id: str) -> list[SessionRoute]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sessions WHERE sandbox_id=? ORDER BY created_at",
                (sandbox_id,),
            ).fetchall()
        return [SessionRoute(**dict(row)) for row in rows]

    def reconcile(self, observed: Iterable[SandboxRecord]) -> list[str]:
        records = list(observed)
        observed_ids: set[str] = set()
        for record in records:
            resolved = self.upsert_sandbox(
                sandbox_id=record.sandbox_id,
                agent_id=record.agent_id,
                username=record.username,
                container_id=record.container_id,
                host_port=record.host_port,
                status=record.status,
                image_version=record.image_version,
                last_active_at=record.last_active_at,
            )
            observed_ids.add(resolved.sandbox_id)
        with self._write_connection() as connection:
            rows = connection.execute("SELECT sandbox_id FROM sandboxes").fetchall()
            missing = [
                row["sandbox_id"]
                for row in rows
                if row["sandbox_id"] not in observed_ids
            ]
            connection.executemany(
                "UPDATE sandboxes SET status='missing', last_active_at=? WHERE sandbox_id=?",
                [(utc_now(), sandbox_id) for sandbox_id in missing],
            )
        return missing
