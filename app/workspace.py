"""Host workspace layout and path-containment helpers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class WorkspacePathError(ValueError):
    """Raised when a caller-controlled path would leave its workspace scope."""


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class WorkspaceLayout:
    """Host paths mounted into one Agent x User sandbox."""

    workspace: Path
    shared: Path
    sessions: Path
    state: Path


class WorkspaceManager:
    """Create isolated workspace layouts and resolve untrusted relative paths."""

    def __init__(
        self,
        workspace_root: str | Path,
        state_root: str | Path,
        *,
        runtime_uid: int | None = None,
        runtime_gid: int | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).expanduser().absolute()
        self.state_root = Path(state_root).expanduser().absolute()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self._workspace_root_real = self.workspace_root.resolve(strict=True)
        self._state_root_real = self.state_root.resolve(strict=True)
        self.runtime_uid = runtime_uid
        self.runtime_gid = runtime_gid

    def ensure_user_layout(self, agent_id: str, username: str) -> WorkspaceLayout:
        """Create and return the persistent layout for one Agent x User pair."""

        agent = validate_identifier(agent_id, "agent_id")
        user = validate_identifier(username, "username")
        guard = getattr(self, 'user_guard', None)
        if guard:
            guard(agent, user)

        workspace = self._create_directory(
            self.workspace_root, self._workspace_root_real, agent, user
        )
        shared = self._create_directory(workspace, workspace, "shared")
        sessions = self._create_directory(workspace, workspace, "sessions")
        state = self._create_directory(
            self.state_root, self._state_root_real, agent, user, "opencode"
        )
        self._set_runtime_ownership(workspace, shared, sessions, state)
        return WorkspaceLayout(workspace, shared, sessions, state)

    def _set_runtime_ownership(self, *paths: Path) -> None:
        if os.name != "posix" or self.runtime_uid is None:
            return
        gid = self.runtime_gid if self.runtime_gid is not None else self.runtime_uid
        for path in paths:
            try:
                os.chown(path, self.runtime_uid, gid)
                path.chmod(0o770)
            except PermissionError as exc:
                raise WorkspacePathError(
                    f"cannot assign {path} to sandbox UID:GID {self.runtime_uid}:{gid}"
                ) from exc

    def resolve_user_path(
        self,
        agent_id: str,
        username: str,
        relative_path: str | Path,
        session_id: str | None = None,
        *,
        create_parent: bool = True,
    ) -> Path:
        """Resolve a path inside shared storage or a named session directory.

        Existing symlinks are followed during validation. A path is returned only
        when its canonical target remains inside the selected shared/session root.
        Parent directories are created after that validation and checked again.
        """

        parts = _relative_parts(relative_path)
        layout = self.ensure_user_layout(agent_id, username)

        if session_id is None:
            scope = layout.shared
        else:
            session = validate_identifier(session_id, "session_id")
            scope = self._create_directory(layout.sessions, layout.workspace, session)
        self._set_runtime_ownership(scope)

        scope_real = scope.resolve(strict=True)
        candidate = scope.joinpath(*parts)
        resolved = self._resolve_contained(candidate, scope_real)

        if create_parent and parts:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            resolved = self._resolve_contained(candidate, scope_real)
            current = candidate.parent
            while current != scope:
                self._set_runtime_ownership(self._resolve_contained(current, scope_real))
                current = current.parent
        return resolved

    def user_scope(
        self, agent_id: str, username: str, session_id: str | None = None
    ) -> Path:
        """Return the shared or session root after validating all identifiers."""

        layout = self.ensure_user_layout(agent_id, username)
        if session_id is None:
            return layout.shared
        session = validate_identifier(session_id, "session_id")
        scope = self._create_directory(layout.sessions, layout.workspace, session)
        self._set_runtime_ownership(scope)
        return scope

    @staticmethod
    def _resolve_contained(candidate: Path, root_real: Path) -> Path:
        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise WorkspacePathError(f"cannot resolve workspace path: {exc}") from exc
        if not resolved.is_relative_to(root_real):
            raise WorkspacePathError("path escapes the selected workspace scope")
        return resolved

    @classmethod
    def _create_directory(
        cls, lexical_root: Path, containment_root: Path, *parts: str
    ) -> Path:
        candidate = lexical_root.joinpath(*parts)
        resolved = cls._resolve_contained(candidate, containment_root)
        candidate.mkdir(parents=True, exist_ok=True)
        resolved = cls._resolve_contained(candidate, containment_root)
        if not resolved.is_dir():
            raise WorkspacePathError(f"workspace path is not a directory: {candidate}")
        return resolved


def validate_identifier(value: str, field: str = "identifier") -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise WorkspacePathError(
            f"{field} must be 1-128 ASCII letters, digits, dots, underscores, or hyphens"
        )
    if value in {".", ".."}:
        raise WorkspacePathError(f"{field} cannot be {value!r}")
    return value


def normalize_relative_parts(value: str | Path) -> tuple[str, ...]:
    raw = str(value)
    if "\x00" in raw:
        raise WorkspacePathError("relative path contains a NUL byte")
    if "\\" in raw:
        raise WorkspacePathError("relative path must use forward slashes")
    if raw.startswith("/") or raw.startswith("//") or _WINDOWS_DRIVE.match(raw):
        raise WorkspacePathError("absolute paths are not allowed")

    path = PurePosixPath(raw)
    if path.is_absolute():
        raise WorkspacePathError("absolute paths are not allowed")
    if ".." in path.parts:
        raise WorkspacePathError("parent traversal is not allowed")
    return tuple(part for part in path.parts if part not in {"", "."})


_relative_parts = normalize_relative_parts
