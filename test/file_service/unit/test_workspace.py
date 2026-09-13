from __future__ import annotations

import os
from pathlib import Path

import pytest

from file_service.workspace import WorkspaceManager, WorkspacePathError


def _symlink_or_skip(target: Path, link: Path, *, directory: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=directory)
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows account lacks symlink creation privilege")
        raise


@pytest.fixture
def manager(tmp_path: Path) -> WorkspaceManager:
    return WorkspaceManager(tmp_path / "workspaces", tmp_path / "state")


def test_creates_expected_agent_user_layout(manager: WorkspaceManager) -> None:
    layout = manager.ensure_user_layout("agent-code", "alice")

    assert layout.workspace == manager.workspace_root / "agent-code" / "alice"
    assert layout.shared.is_dir()
    assert layout.sessions.is_dir()
    assert layout.state == manager.state_root / "agent-code" / "alice" / "opencode"
    assert layout.state.is_dir()


def test_resolves_shared_path_and_creates_parent_after_validation(
    manager: WorkspaceManager,
) -> None:
    target = manager.resolve_user_path("agent-code", "alice", "normal/file.txt")

    assert target == manager.workspace_root / "agent-code" / "alice" / "shared" / "normal" / "file.txt"
    assert target.parent.is_dir()


def test_resolves_session_path(manager: WorkspaceManager) -> None:
    target = manager.resolve_user_path(
        "agent-code", "alice", "outputs/result.xlsx", session_id="ses_123"
    )

    assert target == manager.workspace_root / "agent-code" / "alice" / "sessions" / "ses_123" / "outputs" / "result.xlsx"
    assert target.parent.is_dir()


@pytest.mark.parametrize(
    "untrusted",
    [
        "../bob/file.txt",
        "../../../../etc/passwd",
        "/etc/passwd",
        r"C:\Windows\system.ini",
        r"\\server\share\file.txt",
        "normal\\file.txt",
        "bad\x00name",
    ],
)
def test_rejects_absolute_traversal_and_nonportable_paths(
    manager: WorkspaceManager, untrusted: str
) -> None:
    with pytest.raises(WorkspacePathError):
        manager.resolve_user_path("agent-code", "alice", untrusted)


@pytest.mark.parametrize(
    ("field", "value"),
    [("agent_id", "../agent"), ("username", "alice/bob"), ("session_id", "../ses")],
)
def test_rejects_unsafe_identity_components(
    manager: WorkspaceManager, field: str, value: str
) -> None:
    args = {"agent_id": "agent-code", "username": "alice", "session_id": "ses_1"}
    args[field] = value
    with pytest.raises(WorkspacePathError):
        manager.resolve_user_path(
            args["agent_id"], args["username"], "file.txt", session_id=args["session_id"]
        )


def test_rejected_path_does_not_create_its_parent(manager: WorkspaceManager) -> None:
    outside = manager.workspace_root / "agent-code" / "bob"

    with pytest.raises(WorkspacePathError):
        manager.resolve_user_path("agent-code", "alice", "../bob/new/file.txt")

    assert not outside.exists()


def test_rejects_symlinked_parent_that_escapes_workspace(
    manager: WorkspaceManager, tmp_path: Path
) -> None:
    layout = manager.ensure_user_layout("agent-code", "alice")
    outside = tmp_path / "outside"
    outside.mkdir()
    _symlink_or_skip(outside, layout.shared / "escape", directory=True)

    with pytest.raises(WorkspacePathError):
        manager.resolve_user_path("agent-code", "alice", "escape/secret.txt")

    assert not (outside / "secret.txt").exists()


def test_rejects_existing_file_symlink_that_escapes_workspace(
    manager: WorkspaceManager, tmp_path: Path
) -> None:
    layout = manager.ensure_user_layout("agent-code", "alice")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    _symlink_or_skip(outside, layout.shared / "secret.txt")

    with pytest.raises(WorkspacePathError):
        manager.resolve_user_path("agent-code", "alice", "secret.txt")


def test_rejects_preexisting_user_root_symlink(
    manager: WorkspaceManager, tmp_path: Path
) -> None:
    outside = tmp_path / "outside-user"
    outside.mkdir()
    agent_root = manager.workspace_root / "agent-code"
    agent_root.mkdir()
    _symlink_or_skip(outside, agent_root / "alice", directory=True)

    with pytest.raises(WorkspacePathError):
        manager.ensure_user_layout("agent-code", "alice")

    assert not (outside / "shared").exists()


def test_runtime_ownership_skips_syscalls_when_already_correct(
    tmp_path: Path, monkeypatch
) -> None:
    manager = WorkspaceManager(
        tmp_path / "workspaces",
        tmp_path / "state",
        runtime_uid=os.getuid(),
        runtime_gid=os.getgid(),
    )
    manager.ensure_user_layout("agent-code", "alice")
    chowns = []
    chmods = []
    monkeypatch.setattr(os, "chown", lambda *args: chowns.append(args))
    monkeypatch.setattr(
        Path,
        "chmod",
        lambda self, mode, *args, **kwargs: chmods.append((self, mode)),
    )

    manager.ensure_user_layout("agent-code", "alice")

    assert chowns == []
    assert chmods == []


def test_runtime_ownership_repairs_incorrect_mode(tmp_path: Path) -> None:
    manager = WorkspaceManager(
        tmp_path / "workspaces",
        tmp_path / "state",
        runtime_uid=os.getuid(),
        runtime_gid=os.getgid(),
    )
    layout = manager.ensure_user_layout("agent-code", "alice")
    layout.shared.chmod(0o700)

    repaired = manager.ensure_user_layout("agent-code", "alice")

    assert repaired.shared.stat().st_mode & 0o777 == 0o770
