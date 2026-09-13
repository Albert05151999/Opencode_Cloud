import asyncio
import hashlib
import json
import logging

import pytest

from shared_libs.logging import (
    RequestLogMiddleware,
    TRACE_CONTEXT,
    _SafeJSONFormatter,
    bind_request,
    safe_request_id,
    timed_stage,
)


def test_request_id_and_username_are_safe() -> None:
    assert safe_request_id("req.good:1-2") == "req.good:1-2"
    assert safe_request_id("bad value").startswith("req_")
    assert safe_request_id("é").startswith("req_")
    scope = {}
    context = bind_request(
        scope, request_id="request-1", username="alice", agent_id="agent-code"
    )
    assert context["username_hash"] == hashlib.sha256(b"alice").hexdigest()[:16]
    assert "username" not in context and "alice" not in repr(scope)


def test_formatter_drops_third_party_message_exception_and_extra() -> None:
    sentinel = "SECRET-token-header-body-binary"
    try:
        raise RuntimeError(sentinel)
    except RuntimeError:
        record = logging.LogRecord(
            "third.party",
            logging.ERROR,
            __file__,
            1,
            sentinel,
            (),
            __import__("sys").exc_info(),
        )
    record.headers = {"Authorization": sentinel}
    rendered = _SafeJSONFormatter().format(record)
    payload = json.loads(rendered)
    assert sentinel not in rendered
    assert payload == {
        "component": "third.party",
        "action": "log",
        "timestamp": payload["timestamp"],
        "level": "ERROR",
        "error_code": "RuntimeError",
        "module": payload["module"],
        "instance_id": payload["instance_id"],
        "service_version": payload["service_version"],
    }


def test_formatter_allows_safe_http_and_stage_observation_fields() -> None:
    record = logging.LogRecord("cloud", logging.INFO, __file__, 1, "ignored", (), None)
    record.cloud_payload = {
        "method": "POST",
        "path": "/session/example/message",
        "stage": "ready",
        "duration_ms": 12.5,
        "query": "token=must-not-be-logged",
    }
    rendered = _SafeJSONFormatter().format(record)
    payload = json.loads(rendered)
    assert payload["method"] == "POST"
    assert payload["path"] == "/session/example/message"
    assert payload["stage"] == "ready"
    assert payload["duration_ms"] == 12.5
    assert "must-not-be-logged" not in rendered


def test_middleware_sets_final_request_id_and_does_not_buffer_sse(monkeypatch) -> None:
    emitted = []
    monkeypatch.setattr(
        "shared_libs.logging.emit",
        lambda action, **fields: emitted.append((action, fields)),
    )
    first_sent = asyncio.Event()
    allow_second = asyncio.Event()

    async def app(scope, receive, send):
        bind_request(scope, request_id="final-id", username="alice")
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"x-cloud-request-id", b"old")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"data: first\n\n",
                "more_body": True,
            }
        )
        first_sent.set()
        await allow_second.wait()
        await send(
            {
                "type": "http.response.body",
                "body": b"data: second\n\n",
                "more_body": False,
            }
        )

    sent = []

    async def send(message):
        sent.append(message)

    async def exercise():
        task = asyncio.create_task(
            RequestLogMiddleware(app)(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/event?embedded=must-not-be-logged",
                    "query_string": b"token=must-not-be-logged",
                    "headers": [
                        (b"x-cloud-request-id", b"incoming"),
                        (b"authorization", b"Bearer must-not-be-logged"),
                    ],
                },
                lambda: None,
                send,
            )
        )
        await asyncio.wait_for(first_sent.wait(), 1)
        assert len(sent) == 2 and sent[1]["body"] == b"data: first\n\n"
        assert not task.done()
        allow_second.set()
        await task

    asyncio.run(exercise())
    headers = sent[0]["headers"]
    assert [
        (name, value) for name, value in headers if name == b"x-cloud-request-id"
    ] == [(b"x-cloud-request-id", b"final-id")]
    assert len([value for name, value in headers if name == b"traceparent"]) == 1
    assert len([value for name, value in headers if name == b"x-cloud-trace-id"]) == 1
    assert emitted[0][0] == "http_request" and emitted[0][1]["status_code"] == 200
    assert emitted[0][1]["method"] == "GET"
    assert emitted[0][1]["path"] == "/event"
    assert "must-not-be-logged" not in repr(emitted)
    assert "username" not in emitted[0][1]


def test_timed_stage_is_a_child_span_and_restores_parent(monkeypatch) -> None:
    emitted = []
    monkeypatch.setattr(
        "shared_libs.logging.emit",
        lambda action, **fields: emitted.append((action, fields)),
    )
    parent = {
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "request_id": "request-1",
    }
    token = TRACE_CONTEXT.set(parent)
    try:
        with timed_stage("lock_wait") as stage_context:
            assert stage_context["trace_id"] == parent["trace_id"]
            assert stage_context["span_id"] != parent["span_id"]
            assert stage_context["parent_span_id"] == parent["span_id"]
            assert TRACE_CONTEXT.get() == stage_context
        assert TRACE_CONTEXT.get() == parent
    finally:
        TRACE_CONTEXT.reset(token)
    action, fields = emitted[0]
    assert action == "stage_complete"
    assert fields["stage"] == "lock_wait"
    assert fields["trace_id"] == parent["trace_id"]
    assert fields["parent_span_id"] == parent["span_id"]
    assert fields["duration_ms"] >= 0
    assert fields["error_code"] is None


def test_timed_stage_records_error_type_without_error_text(monkeypatch) -> None:
    emitted = []
    monkeypatch.setattr(
        "shared_libs.logging.emit",
        lambda action, **fields: emitted.append((action, fields)),
    )
    with pytest.raises(RuntimeError, match="secret detail"):
        with timed_stage("catalog"):
            raise RuntimeError("secret detail")
    assert emitted[0][1]["error_code"] == "RuntimeError"
    assert "secret detail" not in repr(emitted)


def test_middleware_logs_failure_and_reraises(monkeypatch) -> None:
    emitted = []
    monkeypatch.setattr(
        "shared_libs.logging.emit",
        lambda action, **fields: emitted.append((action, fields)),
    )

    async def failed(scope, receive, send):
        raise ValueError("secret failure detail")

    with pytest.raises(ValueError, match="secret failure detail"):
        asyncio.run(
            RequestLogMiddleware(failed)(
                {"type": "http", "headers": []}, lambda: None, lambda message: None
            )
        )
    assert emitted[0][1]["status_code"] == 500
    assert emitted[0][1]["error_code"] == "ValueError"


@pytest.mark.parametrize("status,level", [(404, logging.WARNING), (503, logging.ERROR)])
def test_middleware_uses_status_appropriate_log_level(caplog, status, level) -> None:
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def send(message):
        return None

    with caplog.at_level(logging.INFO, logger="cloud"):
        asyncio.run(
            RequestLogMiddleware(app)(
                {"type": "http", "method": "GET", "path": "/safe", "headers": []},
                lambda: None,
                send,
            )
        )
    assert caplog.records[-1].levelno == level


def test_middleware_keeps_trace_and_session_context_isolated(monkeypatch) -> None:
    emitted = []
    monkeypatch.setattr(
        "shared_libs.logging.emit",
        lambda action, **fields: emitted.append((action, fields)),
    )

    async def app(scope, receive, send):
        await asyncio.sleep(0)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def call(index):
        sent = []
        async def capture(message):
            sent.append(message)
        trace = str(index) * 32
        await RequestLogMiddleware(app)(
            {
                "type": "http",
                "method": "POST",
                "path": f"/session/ses_{index}/prompt_async",
                "headers": [(b"traceparent", f"00-{trace}-{'a' * 16}-01".encode())],
            },
            lambda: None,
            capture,
        )
        return sent[0]

    responses = asyncio.run(_gather_calls(call))
    by_session = {fields["session_id"]: fields for _, fields in emitted}
    assert by_session["ses_1"]["trace_id"] == "1" * 32
    assert by_session["ses_2"]["trace_id"] == "2" * 32
    assert {dict(response["headers"])[b"x-cloud-trace-id"] for response in responses} == {
        b"1" * 32,
        b"2" * 32,
    }


async def _gather_calls(call):
    return await asyncio.gather(call(1), call(2))
