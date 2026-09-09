from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from app.registry import Registry, SandboxRecord, SessionRoute


def registry(tmp_path: Path) -> Registry:
    value = Registry(tmp_path / "platform.db")
    value.initialize()
    value.upsert_agent("agent-code", "/agents/agent-code", "cloud-agent-runtime:dev")
    return value


def test_agent_registration_only_updates_when_definition_changes(tmp_path, monkeypatch):
    value = registry(tmp_path)
    with value.connect() as connection:
        before = dict(connection.execute('SELECT * FROM agents').fetchone())
    monkeypatch.setattr('app.registry.utc_now', lambda: '2099-01-01T00:00:00+00:00')
    value.upsert_agent('agent-code', '/agents/agent-code', 'cloud-agent-runtime:dev')
    with value.connect() as connection:
        assert dict(connection.execute('SELECT * FROM agents').fetchone()) == before
    value.upsert_agent('agent-code', '/agents/new', 'new-image', False)
    with value.connect() as connection:
        after = dict(connection.execute('SELECT * FROM agents').fetchone())
    assert after['config_path'] == '/agents/new'
    assert after['image'] == 'new-image'
    assert after['enabled'] == 0
    assert after['updated_at'] == '2099-01-01T00:00:00+00:00'


def test_connection_closes_and_failed_transaction_rolls_back(tmp_path):
    value = registry(tmp_path)
    with pytest.raises(RuntimeError):
        with value.connect() as connection:
            connection.execute("UPDATE agents SET enabled=0")
            raise RuntimeError('rollback')
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute('SELECT 1')
    with value.connect() as reopened:
        assert reopened.execute('SELECT enabled FROM agents').fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError):
        reopened.execute('SELECT 1')


def add_sandbox(value: Registry, sandbox_id: str = "sbx-1") -> SandboxRecord:
    return value.upsert_sandbox(
        sandbox_id=sandbox_id, agent_id="agent-code", username="alice",
        container_id="container-old", host_port=41000, status="ready",
        image_version="dev",
    )


def test_wal_create_update_and_restart_persistence(tmp_path: Path) -> None:
    value = registry(tmp_path)
    created = add_sandbox(value)
    assert created.sandbox_id == "sbx-1"
    updated = value.upsert_sandbox(
        sandbox_id="ignored-new-id", agent_id="agent-code", username="alice",
        container_id="container-new", host_port=42000, status="ready",
        image_version="dev-2",
    )
    assert updated.sandbox_id == "sbx-1"
    assert updated.container_id == "container-new"
    assert value.mark_sandbox_status("sbx-1", "stopped")
    reopened = Registry(tmp_path / "platform.db")
    reopened.initialize()
    assert reopened.get_sandbox("agent-code", "alice").status == "stopped"
    with reopened.connect() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_session_route_owner_and_listing(tmp_path: Path) -> None:
    value = registry(tmp_path)
    add_sandbox(value)
    route = value.record_session("ses-1", "sbx-1", "agent-code", "alice", "sessions/ses-1")
    assert value.get_session_route("ses-1") == route
    assert value.list_sessions_for_sandbox("sbx-1") == [route]
    with pytest.raises(ValueError, match="owner"):
        value.record_session("ses-bad", "sbx-1", "agent-code", "bob", "sessions/ses-bad")


def test_session_batch_isolates_invalid_entries_and_persists_full_sync(tmp_path: Path, monkeypatch) -> None:
    value = registry(tmp_path)
    first = add_sandbox(value)
    value.upsert_agent("agent-review", "/agents/agent-review", "cloud-agent-runtime:dev")
    second = value.upsert_sandbox(
        sandbox_id="sbx-2", agent_id="agent-review", username="bob",
        container_id="container-2", host_port=41001, status="ready", image_version="dev",
    )
    first_active_at = first.last_active_at
    second_active_at = second.last_active_at
    timestamps = iter(f"2099-01-01T00:00:0{index}+00:00" for index in range(1, 6))
    monkeypatch.setattr("app.registry.utc_now", lambda: next(timestamps))

    results = value.record_sessions_batch([
        ("ses-1", "sbx-1", "agent-code", "alice", "sessions/ses-1"),
        ("ses-unknown", "missing", "agent-code", "alice", "sessions/ses-unknown"),
        ("ses-owner", "sbx-1", "agent-code", "bob", "sessions/ses-owner"),
        ("ses-1", "sbx-2", "agent-review", "bob", "sessions/conflict"),
        ("ses-2", "sbx-2", "agent-review", "bob", "sessions/ses-2"),
    ])

    assert isinstance(results[0], SessionRoute)
    assert isinstance(results[1], KeyError)
    assert isinstance(results[2], ValueError)
    assert isinstance(results[3], ValueError)
    assert isinstance(results[4], SessionRoute)
    assert "Unknown sandbox" in str(results[1])
    assert "owner" in str(results[2])
    assert "another route" in str(results[3])
    assert value.get_session_route("ses-unknown") is None
    assert value.get_session_route("ses-owner") is None
    assert value.get_session_route("ses-1").sandbox_id == "sbx-1"
    assert value.get_session_route("ses-1").last_active_at == "2099-01-01T00:00:01+00:00"
    assert value.get_session_route("ses-2").sandbox_id == "sbx-2"
    assert value.get_sandbox("agent-code", "alice").last_active_at > first_active_at
    assert value.get_sandbox("agent-review", "bob").last_active_at > second_active_at
    with value.connect() as connection:
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2

    reopened = Registry(tmp_path / "platform.db")
    reopened.initialize()
    assert reopened.get_session_route("ses-1").workspace_relpath == "sessions/ses-1"
    assert reopened.get_session_route("ses-2").workspace_relpath == "sessions/ses-2"
    with reopened.connect() as connection:
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2


def test_concurrent_upsert_keeps_one_sandbox_per_agent_user(tmp_path: Path) -> None:
    value = registry(tmp_path)

    def create(index: int) -> str:
        return value.upsert_sandbox(
            sandbox_id=f"sbx-{index}", agent_id="agent-code", username="alice",
            container_id=f"container-{index}", host_port=41000 + index,
            status="ready", image_version="dev",
        ).sandbox_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(create, range(32)))
    assert len(set(ids)) == 1
    with value.connect() as connection:
        count = connection.execute(
            "SELECT count(*) FROM sandboxes WHERE agent_id='agent-code' AND username='alice'"
        ).fetchone()[0]
    assert count == 1


def test_lifetime_keeps_wal_without_pinning_checkpoint(tmp_path: Path) -> None:
    value = registry(tmp_path)
    add_sandbox(value)
    wal = Path(str(value.path) + '-wal')
    with value.lifetime():
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: value.touch_sandbox('sbx-1'), range(32)))
        assert wal.exists()
        with value.connect() as connection:
            # NORMAL is connection-local to activity updates only.
            assert connection.execute('PRAGMA synchronous').fetchone()[0] == 2
            assert tuple(connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()) == (0, 0, 0)
        assert value.get_sandbox('agent-code', 'alice').status == 'ready'
    assert not wal.exists()


def test_concurrent_route_lookups(tmp_path: Path) -> None:
    value = registry(tmp_path)
    add_sandbox(value)
    value.record_session("ses-1", "sbx-1", "agent-code", "alice", "sessions/ses-1")
    with ThreadPoolExecutor(max_workers=16) as pool:
        routes = list(pool.map(lambda _: value.get_session_route("ses-1"), range(128)))
    assert all(route and route.username == "alice" for route in routes)


def test_reconcile_marks_unobserved_sandbox_missing(tmp_path: Path) -> None:
    value = registry(tmp_path)
    current = add_sandbox(value)
    missing = value.reconcile([])
    assert missing == [current.sandbox_id]
    assert value.get_sandbox("agent-code", "alice").status == "missing"
    observed = replace(current, status="ready", container_id="new-container")
    assert value.reconcile([observed]) == []
    assert value.get_sandbox("agent-code", "alice").container_id == "new-container"
    rediscovered = replace(observed, sandbox_id="docker-derived-id", container_id="replacement")
    assert value.reconcile([rediscovered]) == []
    assert value.get_sandbox("agent-code", "alice").status == "ready"
