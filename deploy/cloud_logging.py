"""Minimal JSON logging callback for the LiteLLM model gateway."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from litellm.integrations.custom_logger import CustomLogger


_TOKEN = re.compile(r"^[A-Za-z0-9_.:/-]{1,128}$")


def _headers(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    request = value.get("proxy_server_request")
    if not isinstance(request, dict):
        return {}
    headers = request.get("headers")
    if not isinstance(headers, dict):
        return {}
    return {str(key).lower(): item for key, item in headers.items()}


def _request_data(kwargs: Any) -> dict[str, Any]:
    if not isinstance(kwargs, dict):
        return {}
    if isinstance(kwargs.get("proxy_server_request"), dict):
        return kwargs
    params = kwargs.get("litellm_params")
    return params if isinstance(params, dict) else kwargs


def _safe_string(value: Any) -> str | None:
    if isinstance(value, str) and _TOKEN.fullmatch(value):
        return value
    return None


def _duration_ms(start_time: Any, end_time: Any) -> float | None:
    try:
        elapsed = end_time - start_time
        seconds = elapsed.total_seconds() if hasattr(elapsed, "total_seconds") else float(elapsed)
        return round(max(0.0, seconds * 1000), 3)
    except (TypeError, ValueError, OverflowError):
        return None


def _status_code(response_obj: Any, *, success: bool, kwargs: Any = None) -> int | None:
    candidates = [getattr(response_obj, "status_code", None)]
    if isinstance(kwargs, dict):
        candidates.append(getattr(kwargs.get("exception"), "status_code", None))
    for value in candidates:
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    return 200 if success else None


def _error_code(kwargs: Any, response_obj: Any) -> str | None:
    candidates = []
    if isinstance(kwargs, dict):
        candidates.extend((kwargs.get("exception_type"), kwargs.get("error_code")))
        exception = kwargs.get("exception")
        if isinstance(exception, BaseException):
            candidates.append(type(exception).__name__)
    candidates.extend((getattr(response_obj, "code", None), type(response_obj).__name__))
    for value in candidates:
        safe = _safe_string(value)
        if safe:
            return safe
    return None


class CloudModelLogger(CustomLogger):
    @staticmethod
    def _logical_model(data: Any, request: dict[str, Any]) -> str | None:
        candidates = []
        if isinstance(data, dict):
            params = data.get("litellm_params")
            if isinstance(params, dict):
                candidates.append(params.get("model_group"))
                metadata = params.get("metadata")
                if isinstance(metadata, dict):
                    candidates.append(metadata.get("model_group"))
            candidates.append(data.get("model_group"))
        candidates.append(request.get("model"))
        for value in candidates:
            safe = _safe_string(value)
            if safe:
                return safe
        return None

    def _emit(
        self,
        action: str,
        data: Any,
        *,
        status_code: int | None = None,
        duration_ms: float | None = None,
        error_code: str | None = None,
    ) -> None:
        request = _request_data(data)
        headers = _headers(request)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "ERROR" if action == "failure" else "INFO",
            "component": "model_gateway",
            "action": action,
            "request_id": _safe_string(headers.get("x-litellm-trace-id")),
            "session_id": _safe_string(headers.get("x-cloud-session-id")),
            "message_id": _safe_string(headers.get("x-cloud-message-id")),
            "logical_model": self._logical_model(data, request),
            "status_code": status_code,
            "duration_ms": duration_ms,
            "error_code": error_code,
        }
        print(json.dumps(record, separators=(",", ":"), ensure_ascii=True), flush=True)

    async def async_pre_call_hook(self, user_api_key_dict, cache, data: dict, call_type):
        self._emit("pre_call", data)
        return data

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._emit(
            "success",
            kwargs,
            status_code=_status_code(response_obj, success=True),
            duration_ms=_duration_ms(start_time, end_time),
        )

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self._emit(
            "failure",
            kwargs,
            status_code=_status_code(response_obj, success=False, kwargs=kwargs),
            duration_ms=_duration_ms(start_time, end_time),
            error_code=_error_code(kwargs, response_obj),
        )


cloud_logger = CloudModelLogger(turn_off_message_logging=True)
