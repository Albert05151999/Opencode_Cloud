"""Secret-safe structured logging and request correlation."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
import hashlib
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


TRACE_CONTEXT = contextvars.ContextVar("trace_context", default={})
_MODULE = "service"

_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_FIELDS = (
    "timestamp",
    "level",
    "request_id",
    "component",
    "action",
    "agent_id",
    "username_hash",
    "sandbox_id",
    "container_id",
    "session_id",
    "message_id",
    "logical_model",
    "status_code",
    "duration_ms",
    "method",
    "path",
    "stage",
    "error_code",
    "module",
    "instance_id",
    "service_version",
    "trace_id",
    "span_id",
    "parent_span_id",
    "job_id",
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
        bound["username_hash"] = hashlib.sha256(
            str(username).encode("utf-8")
        ).hexdigest()[:16]
    for name, value in fields.items():
        if name in _FIELDS and name not in {"timestamp", "level", "username_hash"}:
            bound[name] = value
    scope["cloud_log"] = bound
    return bound


def emit(action: str, *, log_level: int = logging.INFO, **fields: Any) -> None:
    payload = {
        name: value
        for name, value in {**TRACE_CONTEXT.get(), **fields}.items()
        if name in _FIELDS
    }
    payload["action"] = action
    _LOGGER.log(log_level, "structured_event", extra={"cloud_payload": payload})


@contextmanager
def timed_stage(stage: str, **fields: Any):
    """Emit one bounded timing span beneath the current request or stage span."""
    if not isinstance(stage, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", stage):
        raise ValueError("invalid timing stage")
    parent = dict(TRACE_CONTEXT.get())
    context = {
        **parent,
        "span_id": uuid.uuid4().hex[:16],
        "parent_span_id": parent.get("span_id"),
    }
    token = TRACE_CONTEXT.set(context)
    started = time.perf_counter()
    error_code = None
    try:
        yield context
    except BaseException as exc:
        error_code = type(exc).__name__
        raise
    finally:
        detail = {
            name: value
            for name, value in fields.items()
            if name in _FIELDS
            and name
            not in {"trace_id", "span_id", "parent_span_id", "stage", "duration_ms", "error_code"}
        }
        try:
            emit(
                "stage_complete",
                **context,
                **detail,
                stage=stage,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                error_code=error_code,
            )
        finally:
            TRACE_CONTEXT.reset(token)


class _SafeJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = getattr(record, "cloud_payload", None)
        if isinstance(payload, dict):
            event = {name: payload[name] for name in _FIELDS if name in payload}
            event.setdefault("component", record.name)
            event.setdefault("action", "log")
        else:
            event = {"component": record.name, "action": "log"}
        event.setdefault("module", _MODULE)
        event.setdefault("instance_id", os.environ.get("HOSTNAME", "local"))
        event.setdefault("service_version", os.environ.get("SERVICE_VERSION", "1.0.0"))
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
        event["level"] = record.levelname
        if record.exc_info and record.exc_info[0] is not None:
            event["error_code"] = record.exc_info[0].__name__
        if "container_id" in event and event["container_id"] is not None:
            event["container_id"] = str(event["container_id"])[:12]
        return json.dumps(event, separators=(",", ":"), ensure_ascii=True, default=str)


def configure_logging(
    level: str | int = "INFO",
    *,
    module="service",
    log_root=None,
    max_bytes=10 * 1024 * 1024,
    backup_count=5,
) -> None:
    global _MODULE
    _MODULE = module
    numeric = (
        level if isinstance(level, int) else getattr(logging, str(level).upper(), None)
    )
    if not isinstance(numeric, int):
        raise ValueError(f"invalid logging level: {level}")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_SafeJSONFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(numeric)
    if log_root is not None:
        directory = Path(log_root) / module / os.environ.get("HOSTNAME", "local")
        directory.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            directory / "events.jsonl",
            maxBytes=max(1024, int(max_bytes)),
            backupCount=max(1, int(backup_count)),
        )
        file_handler.setFormatter(_SafeJSONFormatter())
        root.addHandler(file_handler)


class RequestLogMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method", "")).upper()
        if not re.fullmatch(r"[A-Z]{1,16}", method):
            method = "OTHER"
        path = str(scope.get("path", "")).split("?", 1)[0][:2048]
        incoming = None
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-cloud-request-id":
                try:
                    incoming = value.decode("ascii")
                except UnicodeDecodeError:
                    incoming = None
                break
        headers_in = dict(scope.get("headers", []))
        traceparent = headers_in.get(b"traceparent", b"").decode(
            "ascii", errors="ignore"
        )
        match = re.fullmatch(r"00-([0-9a-f]{32})-([0-9a-f]{16})-0[01]", traceparent)
        valid_parent = bool(
            match and int(match[1], 16) and int(match[2], 16)
        )
        trace_id = match[1] if valid_parent else uuid.uuid4().hex
        context = {
            "trace_id": trace_id,
            "span_id": uuid.uuid4().hex[:16],
            "parent_span_id": match[2] if valid_parent else None,
        }
        session_id = headers_in.get(b"x-cloud-session-id", b"").decode(
            "ascii", errors="ignore"
        )
        if not _REQUEST_ID.fullmatch(session_id):
            path_match = re.search(r"(?:^|/)session/([^/]+)(?:/|$)", path)
            session_id = path_match[1] if path_match else ""
        if _REQUEST_ID.fullmatch(session_id):
            context["session_id"] = session_id
        message_id = headers_in.get(b"x-cloud-message-id", b"").decode(
            "ascii", errors="ignore"
        )
        if _REQUEST_ID.fullmatch(message_id):
            context["message_id"] = message_id
        job_id = headers_in.get(b"x-cloud-job-id", b"").decode("ascii", errors="ignore")
        if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job_id):
            context["job_id"] = job_id
        context_token = TRACE_CONTEXT.set(context)
        bind_request(scope, request_id=incoming, method=method, path=path, **context)
        TRACE_CONTEXT.set({**context, "request_id": scope["cloud_log"]["request_id"]})
        started = time.perf_counter()
        status_code = 500
        error_code = None

        async def correlated_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message["status"])
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower()
                    not in {b"x-cloud-request-id", b"x-cloud-trace-id", b"traceparent"}
                ]
                final_request_id = safe_request_id(scope["cloud_log"].get("request_id"))
                scope["cloud_log"]["request_id"] = final_request_id
                headers.append(
                    (b"x-cloud-request-id", final_request_id.encode("ascii"))
                )
                headers.append((b"x-cloud-trace-id", trace_id.encode("ascii")))
                headers.append(
                    (b"traceparent", f"00-{trace_id}-{context['span_id']}-01".encode("ascii"))
                )
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, correlated_send)
        except BaseException as exc:
            error_code = type(exc).__name__
            raise
        finally:
            fields = {
                **scope["cloud_log"],
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "error_code": error_code,
            }
            level = logging.ERROR if error_code or status_code >= 500 else (
                logging.WARNING if status_code >= 400 else logging.INFO
            )
            emit("http_request", log_level=level, **fields)
            TRACE_CONTEXT.reset(context_token)
