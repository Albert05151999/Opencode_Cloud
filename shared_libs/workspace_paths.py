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
