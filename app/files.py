"""Cloud-specific streaming upload, download, and file-list endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from urllib.parse import quote
from weakref import WeakValueDictionary

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, Request
from starlette.responses import StreamingResponse

from app.config import StorageConfig
from app.metrics import PlatformMetrics
from app.workspace import WorkspaceManager, WorkspacePathError, normalize_relative_parts
from app.observability import bind_request


class FileService:
    def __init__(self, config: StorageConfig, workspaces: WorkspaceManager, metrics: PlatformMetrics | None = None) -> None:
        self.config = config
        self.workspaces = workspaces
        self.metrics = metrics
        self._locks: WeakValueDictionary[tuple[str, str], asyncio.Lock] = WeakValueDictionary()

    async def upload(
        self, agent_id: str, username: str, upload: UploadFile,
        relative_path: str | None, session_id: str | None,
    ) -> dict[str, object]:
        destination = relative_path or Path(upload.filename or "").name
        if not destination:
            raise HTTPException(400, "relative_path or a filename is required")
        lock = self._locks.setdefault((agent_id, username), asyncio.Lock())
        async with lock:
            try:
                parent_fd, filename, scope = self._open_parent(
                    agent_id, username, destination, session_id, create=True
                )
            except WorkspacePathError as exc:
                raise HTTPException(400, str(exc)) from exc
            temp_name = f".upload-{secrets.token_hex(16)}.tmp"
            fd: int | None = None
            size = 0
            digest = hashlib.sha256()
            try:
                old_size = self._existing_regular_size(parent_fd, filename)
                used = await asyncio.to_thread(self._tree_size, self.workspaces.ensure_user_layout(agent_id, username).workspace)
                fd = os.open(
                    temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600, dir_fd=parent_fd,
                )
                if self.workspaces.runtime_uid is not None:
                    gid = (
                        self.workspaces.runtime_gid
                        if self.workspaces.runtime_gid is not None
                        else self.workspaces.runtime_uid
                    )
                    os.fchown(fd, self.workspaces.runtime_uid, gid)
                    os.fchmod(fd, 0o660)
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.config.max_upload_mb * 1024 * 1024:
                        raise HTTPException(413, "upload exceeds configured maximum")
                    if used - old_size + size > self.config.max_user_workspace_gb * 1024**3:
                        raise HTTPException(413, "workspace quota exceeded")
                    digest.update(chunk)
                    await asyncio.to_thread(self._write_all, fd, chunk)
                await asyncio.to_thread(os.fsync, fd)
                os.close(fd)
                fd = None
                self._reject_symlink_or_nonregular(parent_fd, filename)
                os.replace(temp_name, filename, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            except WorkspacePathError as exc:
                raise HTTPException(400, str(exc)) from exc
            finally:
                if fd is not None:
                    os.close(fd)
                try:
                    os.unlink(temp_name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
                os.close(parent_fd)
                await upload.close()
        relative = PurePosixPath(*normalize_relative_parts(destination)).as_posix()
        container = f"/workspace/{'sessions/' + session_id if session_id else 'shared'}/{relative}"
        if self.metrics is not None:
            self.metrics.upload_bytes.inc(size)
        return {"ok": True, "path": container, "size": size, "sha256": digest.hexdigest()}

    def open_download(
        self, agent_id: str, username: str, path: str, session_id: str | None,
    ) -> tuple[BinaryIO, str, int]:
        parent_fd, filename, _scope = self._open_parent(
            agent_id, username, path, session_id, create=False
        )
        try:
            try:
                fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
            except FileNotFoundError:
                raise
            except OSError as exc:
                raise WorkspacePathError(f"unsafe download target: {exc}") from exc
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                os.close(fd)
                raise WorkspacePathError("download target is not a regular file")
            return os.fdopen(fd, "rb"), filename, info.st_size
        finally:
            os.close(parent_fd)

    def list_entries(
        self, agent_id: str, username: str, path: str,
        session_id: str | None,
    ) -> list[dict[str, object]]:
        scope = self.workspaces.user_scope(agent_id, username, session_id)
        parts = normalize_relative_parts(path)
        fd = self._walk_directory(scope, parts, create=False)
        try:
            entries = []
            for name in sorted(os.listdir(fd)):
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                kind = "file" if stat.S_ISREG(info.st_mode) else "directory" if stat.S_ISDIR(info.st_mode) else "symlink"
                entries.append({
                    "name": name, "type": kind, "size": info.st_size,
                    "mtime": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                })
            return entries
        finally:
            os.close(fd)

    def _open_parent(
        self, agent_id: str, username: str, path: str,
        session_id: str | None, *, create: bool,
    ) -> tuple[int, str, Path]:
        if os.name != "posix":
            raise WorkspacePathError("secure file operations require Linux")
        parts = normalize_relative_parts(path)
        if not parts:
            raise WorkspacePathError("file path cannot be empty")
        scope = self.workspaces.user_scope(agent_id, username, session_id)
        fd = self._walk_directory(scope, parts[:-1], create=create)
        return fd, parts[-1], scope

    def _walk_directory(self, scope: Path, parts: tuple[str, ...], *, create: bool) -> int:
        fd = os.open(scope, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts:
                if create:
                    try:
                        os.mkdir(part, 0o770, dir_fd=fd)
                        if self.workspaces.runtime_uid is not None:
                            gid = (
                                self.workspaces.runtime_gid
                                if self.workspaces.runtime_gid is not None
                                else self.workspaces.runtime_uid
                            )
                            os.chown(part, self.workspaces.runtime_uid, gid, dir_fd=fd, follow_symlinks=False)
                    except FileExistsError:
                        pass
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                if create and self.workspaces.runtime_uid is not None:
                    os.fchmod(next_fd, 0o770)
                os.close(fd)
                fd = next_fd
            return fd
        except FileNotFoundError:
            os.close(fd)
            raise
        except (OSError, RuntimeError) as exc:
            os.close(fd)
            raise WorkspacePathError(f"unsafe workspace directory: {exc}") from exc

    @staticmethod
    def _existing_regular_size(parent_fd: int, filename: str) -> int:
        try:
            info = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return 0
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise WorkspacePathError("upload target is not a regular file")
        return info.st_size

    @staticmethod
    def _reject_symlink_or_nonregular(parent_fd: int, filename: str) -> None:
        try:
            info = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise WorkspacePathError("upload target is not a regular file")

    @staticmethod
    def _tree_size(root: Path) -> int:
        total = 0
        for directory, _subdirs, files in os.walk(root, followlinks=False):
            for name in files:
                try:
                    info = os.stat(Path(directory) / name, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if stat.S_ISREG(info.st_mode):
                    total += info.st_size
        return total

    @staticmethod
    def _write_all(fd: int, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write while storing upload")
            view = view[written:]


def create_files_router(config: StorageConfig, workspaces: WorkspaceManager, metrics: PlatformMetrics | None = None) -> APIRouter:
    router = APIRouter(prefix="/cloud/files", tags=["cloud-files"])
    service = FileService(config, workspaces, metrics)

    @router.post("/upload")
    async def upload(
        request: Request,
        agent_id: str = Form(), username: str = Form(),
        file: UploadFile = File(), session_id: str | None = Form(None),
        relative_path: str | None = Form(None),
    ) -> dict[str, object]:
        management = getattr(request.app.state, 'management', None)
        if management and management.load_tests.owns_user(username):
            raise HTTPException(409, 'Load-test users only accept the fixed workload, not manual uploads')
        bind_request(request.scope, component="files", agent_id=agent_id, username=username, session_id=session_id)
        return await service.upload(agent_id, username, file, relative_path, session_id)

    @router.get("/download")
    async def download(
        request: Request,
        agent_id: str, username: str, path: str,
        session_id: str | None = None,
    ) -> StreamingResponse:
        bind_request(request.scope, component="files", agent_id=agent_id, username=username, session_id=session_id)
        try:
            handle, filename, size = service.open_download(agent_id, username, path, session_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "file not found") from exc
        except WorkspacePathError as exc:
            raise HTTPException(400, str(exc)) from exc

        async def chunks():
            try:
                while data := await asyncio.to_thread(handle.read, 1024 * 1024):
                    yield data
            finally:
                handle.close()

        raw_ascii = filename.encode("ascii", "ignore").decode()
        ascii_name = "".join(
            character if 32 <= ord(character) < 127 and character not in {'"', "\\"} else "_"
            for character in raw_ascii
        ) or "download"
        encoded_name = quote(filename, safe="")
        return StreamingResponse(
            chunks(), media_type="application/octet-stream",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'
                ),
                "Content-Length": str(size),
            },
        )

    @router.get("/list")
    async def list_files(
        request: Request,
        agent_id: str, username: str, path: str = Query("."),
        session_id: str | None = None,
    ) -> dict[str, object]:
        bind_request(request.scope, component="files", agent_id=agent_id, username=username, session_id=session_id)
        try:
            return {"entries": service.list_entries(agent_id, username, path, session_id)}
        except FileNotFoundError as exc:
            raise HTTPException(404, "directory not found") from exc
        except WorkspacePathError as exc:
            raise HTTPException(400, str(exc)) from exc

    return router
