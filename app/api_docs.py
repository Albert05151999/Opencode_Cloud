"""Static public API documentation derived from the pinned OpenCode schema."""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from starlette.responses import Response


UPSTREAM_SPEC = (
    Path(__file__).resolve().parents[1]
    / "docs" / "upstream" / "opencode-1.18.29-openapi.json"
)
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
ROUTING_PARAMETERS = (
    {
        "name": "X-Cloud-Session-ID", "in": "header", "required": False,
        "schema": {"type": "string"},
        "description": "Session context for directory-scoped permission/question endpoints; must agree with URL and owner metadata. Removed before forwarding.",
    },
    {
        "name": "X-Cloud-Agent-ID", "in": "header", "required": False,
        "schema": {"type": "string"},
        "description": "Agent route metadata for paths that are not already bound to a session.",
    },
    {
        "name": "X-Cloud-Username", "in": "header", "required": False,
        "schema": {"type": "string"},
        "description": "User route metadata; it must agree with an existing session route.",
    },
    {
        "name": "X-Cloud-Request-ID", "in": "header", "required": False,
        "schema": {"type": "string", "pattern": "^[A-Za-z0-9_.:-]{1,128}$"},
        "description": "Optional request correlation identifier.",
    },
)
LEGACY_ACCEPTANCE = {
    "global": ["GET /global/health", "GET /global/event", "GET /event"],
    "sessions": [
        "GET /session", "POST /session", "GET /session/status", "GET /session/{sessionID}",
        "PATCH /session/{sessionID}", "DELETE /session/{sessionID}",
        "GET /session/{sessionID}/message", "POST /session/{sessionID}/message",
        "GET /session/{sessionID}/message/{messageID}",
        "POST /session/{sessionID}/prompt_async", "POST /session/{sessionID}/command",
        "POST /session/{sessionID}/shell",
    ],
    "files_tools_config": [
        "GET /project", "GET /path", "GET /config", "PATCH /config",
        "GET /provider", "GET /file", "GET /file/content", "GET /mcp", "POST /mcp",
        "GET /agent", "GET /command",
    ],
}


def _routing_extension() -> dict[str, Any]:
    return {
        "version": 1,
        "metadata": {
            "json_body": {
                "property": "_cloud",
                "fields": ["agent_id", "username", "session_workspace", "request_id"],
                "behavior": "Removed from JSON objects on POST, PUT and PATCH with application/json content type before forwarding.",
            },
            "headers": [parameter["name"] for parameter in ROUTING_PARAMETERS],
        },
        "resolution": {
            "session_paths": "The session ID is resolved through the durable cloud session-route table.",
            "other_paths": "agent_id and username must be supplied through _cloud or cloud routing headers.",
            "conflicts": "Metadata that disagrees with a durable session route is rejected before forwarding.",
        },
        "native_fields": "Native agent, provider, and model fields retain their upstream meaning and are not overwritten.",
        "session_directory_binding": {
            "since": "0.2.1", "directory": "/workspace/sessions/<sessionID>",
            "initialization": "Create, persist route, bind native directory, read back before returning success.",
            "failure": "Block execution without falling back to the workspace root.",
            "events": "/event unwraps the sandbox-wide global event stream to preserve native event payloads.",
            "blocked_native_paths": ["/experimental/control-plane/move-session", "/experimental/workspace/warp"],
        },
        "legacy_http_scope": LEGACY_ACCEPTANCE,
        "websocket": {
            "pty_supported": False,
            "description": "PTY WebSocket proxying is not implemented in this release.",
        },
    }


def _build_document(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Pinned OpenCode API document is unavailable: {path}") from exc
    try:
        source = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Pinned OpenCode API document is invalid: {path}") from exc
    if not isinstance(source, dict) or source.get("openapi") != "3.1.0" or not isinstance(source.get("paths"), dict):
        raise RuntimeError(f"Pinned OpenCode API document has an unexpected structure: {path}")
    document = copy.deepcopy(source)
    document["x-cloud-routing"] = _routing_extension()
    for path_item in document["paths"].values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            parameters = operation.setdefault("parameters", [])
            existing = {
                (item.get("name", "").lower(), item.get("in"))
                for item in parameters if isinstance(item, dict)
            }
            parameters.extend(
                copy.deepcopy(parameter)
                for parameter in ROUTING_PARAMETERS
                if (parameter["name"].lower(), "header") not in existing
            )
    return document


@lru_cache(maxsize=1)
def _document_bytes() -> bytes:
    return json.dumps(
        _build_document(UPSTREAM_SPEC), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def create_docs_router() -> APIRouter:
    document = _document_bytes()
    router = APIRouter()

    @router.get("/doc", include_in_schema=False)
    async def api_document() -> Response:
        return Response(document, media_type="application/json")

    return router
