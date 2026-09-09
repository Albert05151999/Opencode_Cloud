"""Secret-safe structured logging and request correlation."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_FIELDS = (
    "timestamp", "level", "request_id", "component", "action", "agent_id",
    "username_hash", "sandbox_id", "container_id", "session_id", "message_id",
    "logical_model", "status_code", "duration_ms", "error_code",
)
_LOGGER = logging.getLogger("cloud")


def safe_request_id(value: Any) -> str:
    if isinstance(value, str) and value.isascii() and _REQUEST_ID.fullmatch(value):
        return value
    return "req_" + uuid.uuid4().hex


def bind_request(scope: dict[str, Any], **fields: Any) -> dict[str, Any]:
    bound = dict(scope.get("cloud_log") or {})
    if "request_id" in fields:
        bound["request_id"] = safe_request_id(fields.pop("request_id"))
    else:
        bound.setdefault("request_id", safe_request_id(None))
    username = fields.pop("username", None)
    if username is not None:
        bound["username_hash"] = hashlib.sha256(str(username).encode("utf-8")).hexdigest()[:16]
    for name, value in fields.items():
        if name in _FIELDS and name not in {"timestamp", "level", "username_hash"}:
            bound[name] = value
    scope["cloud_log"] = bound
    return bound


def emit(action: str, **fields: Any) -> None:
    payload = {name: value for name, value in fields.items() if name in _FIELDS}
    payload["action"] = action
    _LOGGER.info("structured_event", extra={"cloud_payload": payload})


class _SafeJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "cloud_payload", None)
        if isinstance(payload, dict):
            event = {name: payload[name] for name in _FIELDS if name in payload}
            event.setdefault("component", record.name)
            event.setdefault("action", "log")
        else:
            event = {"component": record.name, "action": "log"}
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
        event["level"] = record.levelname
        if record.exc_info and record.exc_info[0] is not None:
            event["error_code"] = record.exc_info[0].__name__
        if "container_id" in event and event["container_id"] is not None:
            event["container_id"] = str(event["container_id"])[:12]
        return json.dumps(event, separators=(",", ":"), ensure_ascii=True, default=str)


def configure_logging(level: str | int = "INFO") -> None:
    numeric = level if isinstance(level, int) else getattr(logging, str(level).upper(), None)
    if not isinstance(numeric, int):
        raise ValueError(f"invalid logging level: {level}")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_SafeJSONFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(numeric)


class RequestLogMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        incoming = None
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-cloud-request-id":
                try:
                    incoming = value.decode("ascii")
                except UnicodeDecodeError:
                    incoming = None
                break
        bind_request(scope, request_id=incoming)
        started = time.perf_counter()
        status_code = 500
        error_code = None

        async def correlated_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message["status"])
                headers = [
                    (name, value) for name, value in message.get("headers", [])
                    if name.lower() != b"x-cloud-request-id"
                ]
                final_request_id = safe_request_id(scope["cloud_log"].get("request_id"))
                scope["cloud_log"]["request_id"] = final_request_id
                headers.append((b"x-cloud-request-id", final_request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, correlated_send)
        except BaseException as exc:
            error_code = type(exc).__name__
            raise
        finally:
            fields = {
                **scope["cloud_log"], "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "error_code": error_code,
            }
            emit("http_request", **fields)
