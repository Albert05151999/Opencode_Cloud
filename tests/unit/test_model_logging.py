from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace


custom_logger_module = ModuleType("litellm.integrations.custom_logger")


class FakeCustomLogger:
    def __init__(self, **kwargs) -> None:
        self.options = kwargs


custom_logger_module.CustomLogger = FakeCustomLogger
sys.modules.setdefault("litellm", ModuleType("litellm"))
sys.modules.setdefault("litellm.integrations", ModuleType("litellm.integrations"))
sys.modules.setdefault("litellm.integrations.custom_logger", custom_logger_module)

from deploy.cloud_logging import CloudModelLogger, cloud_logger


ALLOWED = {
    "timestamp", "level", "component", "action", "request_id", "session_id",
    "message_id", "logical_model", "status_code", "duration_ms", "error_code",
}


def read_record(capsys) -> dict:
    line = capsys.readouterr().out.strip()
    assert len(line.splitlines()) == 1
    return json.loads(line)


def request_data() -> dict:
    return {
        "model": "coding-quality",
        "messages": [{"role": "user", "content": "SECRET PROMPT"}],
        "api_key": "sk-secret",
        "proxy_server_request": {
            "headers": {
                "X-LiteLLM-Trace-ID": "msg_native-1",
                "x-cloud-session-id": "ses_123",
                "X-Cloud-Message-ID": "msg_456",
                "Authorization": "Bearer secret",
            },
            "body": {"messages": ["SECRET BODY"]},
        },
    }


def test_pre_call_returns_unmodified_data_and_emits_only_whitelist(capsys) -> None:
    logger = CloudModelLogger()
    data = request_data()
    returned = asyncio.run(logger.async_pre_call_hook(object(), object(), data, "acompletion"))
    record = read_record(capsys)

    assert returned is data
    assert set(record) == ALLOWED
    assert record | {} == {
        **record,
        "level": "INFO", "component": "model_gateway", "action": "pre_call",
        "request_id": "msg_native-1", "session_id": "ses_123",
        "message_id": "msg_456", "logical_model": "coding-quality",
        "status_code": None, "duration_ms": None, "error_code": None,
    }
    serialized = json.dumps(record)
    assert "SECRET" not in serialized and "Authorization" not in serialized and "sk-secret" not in serialized


def test_success_reads_nested_callback_request_and_duration(capsys) -> None:
    logger = CloudModelLogger()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    params = request_data()
    params["model_group"] = "coding-fast"
    kwargs = {"litellm_params": params, "model": "openai/physical-model", "messages": ["SECRET"]}
    asyncio.run(logger.async_log_success_event(kwargs, object(), start, start + timedelta(milliseconds=125.5)))
    record = read_record(capsys)

    assert set(record) == ALLOWED
    assert record["action"] == "success"
    assert record["status_code"] == 200
    assert record["duration_ms"] == 125.5
    assert record["request_id"] == "msg_native-1"
    assert record["logical_model"] == "coding-fast"


def test_failure_logs_safe_code_without_exception_message(capsys) -> None:
    logger = CloudModelLogger()
    kwargs = {"litellm_params": request_data(), "exception": RuntimeError("SECRET upstream body")}
    response = SimpleNamespace(status_code=429, code="rate_limit")
    asyncio.run(logger.async_log_failure_event(kwargs, response, 10.0, 10.25))
    record = read_record(capsys)

    assert set(record) == ALLOWED
    assert record["level"] == "ERROR" and record["action"] == "failure"
    assert record["status_code"] == 429 and record["duration_ms"] == 250.0
    assert record["error_code"] == "RuntimeError"
    assert "SECRET" not in json.dumps(record)


def test_malformed_values_are_not_stringified_into_logs(capsys) -> None:
    logger = CloudModelLogger()
    data = request_data()
    data["model"] = {"secret": "model body"}
    data["proxy_server_request"]["headers"]["x-cloud-session-id"] = "spaces are rejected"
    asyncio.run(logger.async_pre_call_hook(None, None, data, "acompletion"))
    record = read_record(capsys)

    assert record["logical_model"] is None
    assert record["session_id"] is None
    assert set(record) == ALLOWED
    assert cloud_logger.options == {"turn_off_message_logging": True}
