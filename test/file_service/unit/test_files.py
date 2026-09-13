from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException, UploadFile, Request

from shared_libs.config_models import StorageConfig
from file_service.files import FileService, create_files_router
from file_service.workspace import WorkspaceManager, WorkspacePathError


pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="secure file operations are Linux/WSL only"
)


class ChunkedUpload:
    def __init__(self, filename: str, chunks: list[bytes]) -> None:
        self.filename = filename
        self._chunks = iter(chunks)
        self.read_sizes: list[int] = []
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return next(self._chunks, b"")

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def service(tmp_path: Path) -> FileService:
    config = StorageConfig(
        workspace_root=str(tmp_path / "workspaces"),
        state_root=str(tmp_path / "state"),
        max_upload_mb=1,
        max_user_workspace_gb=1,
    )
    return FileService(
        config, WorkspaceManager(config.workspace_root, config.state_root)
    )


def run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def upload(
    service: FileService,
    data: bytes,
    path: str,
    *,
    agent: str = "agent-code",
    user: str = "alice",
    session: str | None = None,
) -> dict[str, object]:
    value = ChunkedUpload(Path(path).name, [data])
    return run(service.upload(agent, user, value, path, session))


def read_download(
    service: FileService,
    path: str,
    *,
    agent: str = "agent-code",
    user: str = "alice",
    session: str | None = None,
) -> bytes:
    handle, _name, _size = service.open_download(agent, user, path, session)
    try:
        return handle.read()
    finally:
        handle.close()


def assert_no_upload_temps(root: Path) -> None:
    assert list(root.rglob(".upload-*.tmp")) == []


def stream_download(service: FileService, path: str) -> tuple[Any, list[bytes]]:
    router = create_files_router(service.config, service.workspaces)
    endpoint = next(route.endpoint for route in router.routes if route.path.endswith("/download"))

    async def consume() -> tuple[Any, list[bytes]]:
        response = await endpoint(
            request=Request({"type": "http", "headers": []}),
            agent_id="agent-code",
            username="alice",
            path=path,
            session_id=None,
        )
        return response, [chunk async for chunk in response.body_iterator]

    return run(consume())


def assert_path_rejected(
    service: FileService,
    path: str,
    *,
    upload_path: str | None = None,
    list_path: str | None = None,
) -> None:
    rejected_upload = upload_path or path
    value = ChunkedUpload(Path(rejected_upload).name, [b"new"])
    with pytest.raises(HTTPException) as upload_error:
        run(service.upload("agent-code", "alice", value, rejected_upload, None))
    assert upload_error.value.status_code == 400
    with pytest.raises(WorkspacePathError):
        service.open_download("agent-code", "alice", path, None)
    with pytest.raises(WorkspacePathError):
        service.list_entries("agent-code", "alice", list_path or path, None)


def test_shared_and_session_upload_return_path_size_and_sha256(
    service: FileService,
) -> None:
    shared = b"shared bytes"
    session = b"session bytes"
    shared_result = upload(service, shared, "inputs/shared.bin")
    session_result = upload(
        service, session, "inputs/session.bin", session="ses_123"
    )

    assert shared_result == {
        "ok": True,
        "path": "/workspace/shared/inputs/shared.bin",
        "size": len(shared),
        "sha256": hashlib.sha256(shared).hexdigest(),
    }
    assert session_result == {
        "ok": True,
        "path": "/workspace/sessions/ses_123/inputs/session.bin",
        "size": len(session),
        "sha256": hashlib.sha256(session).hexdigest(),
    }
    assert read_download(service, "inputs/shared.bin") == shared
    assert read_download(service, "inputs/session.bin", session="ses_123") == session


def test_download_router_preserves_bytes_hash_and_safe_utf8_disposition(
    service: FileService,
) -> None:
    data = b"\x00\xffdownload-content"
    name = '报告 "final".bin'
    result = upload(service, data, name)
    response, chunks = stream_download(service, name)
    body = b"".join(chunks)
    disposition = response.headers["content-disposition"]
    assert body == data
    assert hashlib.sha256(body).hexdigest() == result["sha256"]
    assert response.headers["content-type"] == "application/octet-stream"
    assert 'filename="' in disposition
    assert 'filename*=UTF-8\'\'' in disposition
    assert "%E6%8A%A5%E5%91%8A" in disposition
    assert "\r" not in disposition and "\n" not in disposition


def test_list_returns_sorted_file_and_directory_metadata(
    service: FileService,
) -> None:
    upload(service, b"abc", "out/z.bin")
    upload(service, b"x", "out/sub/a.txt")

    entries = service.list_entries("agent-code", "alice", "out", None)
    assert [entry["name"] for entry in entries] == ["sub", "z.bin"]
    assert entries[0]["type"] == "directory"
    assert entries[1]["type"] == "file"
    assert entries[1]["size"] == 3
    assert isinstance(entries[1]["mtime"], str)
    assert entries[1]["mtime"].endswith("+00:00")


def test_oversized_upload_fails_without_target_or_temp(
    service: FileService,
) -> None:
    scope = service.workspaces.user_scope("agent-code", "alice")
    value = ChunkedUpload("too-large.bin", [b"a" * (1024 * 1024), b"x"])

    with pytest.raises(HTTPException) as caught:
        run(service.upload("agent-code", "alice", value, "too-large.bin", None))

    assert caught.value.status_code == 413
    assert not (scope / "too-large.bin").exists()
    assert_no_upload_temps(scope)
    assert value.closed is True


def test_workspace_quota_failure_keeps_existing_target_and_no_temp(
    service: FileService, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = b"original"
    upload(service, original, "kept.bin")
    scope = service.workspaces.user_scope("agent-code", "alice")
    monkeypatch.setattr(
        service,
        "_tree_size",
        lambda _root: service.config.max_user_workspace_gb * 1024**3,
    )

    with pytest.raises(HTTPException) as caught:
        upload(service, b"replacement", "new.bin")

    assert caught.value.status_code == 413
    assert read_download(service, "kept.bin") == original
    assert not (scope / "new.bin").exists()
    assert_no_upload_temps(scope)


def test_overwrite_atomically_replaces_existing_content(
    service: FileService, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload(service, b"old", "result.bin")
    replacements: list[tuple[str, str]] = []
    real_replace = os.replace

    def observe_replace(
        source: str, destination: str, *, src_dir_fd: int, dst_dir_fd: int
    ) -> None:
        replacements.append((source, destination))
        real_replace(
            source, destination, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd
        )

    monkeypatch.setattr(os, "replace", observe_replace)
    result = upload(service, b"new-content", "result.bin")

    assert read_download(service, "result.bin") == b"new-content"
    assert result["sha256"] == hashlib.sha256(b"new-content").hexdigest()
    assert len(replacements) == 1
    assert replacements[0][0].startswith(".upload-")
    assert replacements[0][1] == "result.bin"
    assert_no_upload_temps(service.workspaces.workspace_root)


@pytest.mark.parametrize("unsafe", ["../escape.bin", "/etc/passwd"])
def test_traversal_and_absolute_paths_fail_for_all_operations(
    service: FileService, unsafe: str
) -> None:
    assert_path_rejected(service, unsafe)


def test_parent_directory_symlink_fails_upload_download_and_list(
    service: FileService, tmp_path: Path
) -> None:
    scope = service.workspaces.user_scope("agent-code", "alice")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.bin").write_bytes(b"secret")
    os.symlink(outside, scope / "escape", target_is_directory=True)

    assert_path_rejected(
        service,
        "escape/secret.bin",
        upload_path="escape/new.bin",
        list_path="escape",
    )
    assert not (outside / "new.bin").exists()
    assert_no_upload_temps(scope)


def test_target_file_symlink_fails_upload_download_and_list_path(
    service: FileService, tmp_path: Path
) -> None:
    scope = service.workspaces.user_scope("agent-code", "alice")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"secret")
    os.symlink(outside, scope / "linked.bin")

    assert_path_rejected(service, "linked.bin")
    assert outside.read_bytes() == b"secret"
    assert_no_upload_temps(scope)


def test_bob_parameters_cannot_address_alice_workspace(
    service: FileService,
) -> None:
    upload(service, b"alice-secret", "private/data.bin", user="alice")
    with pytest.raises(FileNotFoundError):
        service.open_download("agent-code", "bob", "private/data.bin", None)
    with pytest.raises(FileNotFoundError):
        service.list_entries("agent-code", "bob", "private", None)
    bob_result = upload(service, b"bob-data", "private/data.bin", user="bob")
    assert bob_result["path"] == "/workspace/shared/private/data.bin"
    assert read_download(service, "private/data.bin", user="alice") == b"alice-secret"
    assert read_download(service, "private/data.bin", user="bob") == b"bob-data"


def test_large_upload_and_download_use_bounded_chunks(
    service: FileService, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.config = StorageConfig(
        service.config.workspace_root,
        service.config.state_root,
        max_upload_mb=5,
        max_user_workspace_gb=service.config.max_user_workspace_gb,
    )
    chunk = b"x" * (512 * 1024)
    value = ChunkedUpload("large.bin", [chunk] * 5)
    result = run(
        service.upload("agent-code", "alice", value, "large.bin", None)
    )
    expected_size = 5 * 512 * 1024
    assert result["size"] == expected_size
    assert value.read_sizes == [1024 * 1024] * 6

    handle, _, _ = service.open_download("agent-code", "alice", "large.bin", None)
    read_sizes: list[int] = []

    class ObservedHandle:
        def read(self, size: int) -> bytes:
            read_sizes.append(size)
            return handle.read(size)

        def close(self) -> None:
            handle.close()

    monkeypatch.setattr(
        FileService,
        "open_download",
        lambda _self, *_args: (ObservedHandle(), "large.bin", expected_size),
    )

    _, downloaded_chunks = stream_download(service, "large.bin")
    assert b"".join(downloaded_chunks) == chunk * 5
    assert len(downloaded_chunks) == 3
    assert read_sizes == [1024 * 1024] * 4
    assert all(len(part) <= 1024 * 1024 for part in downloaded_chunks)
