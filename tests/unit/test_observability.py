import asyncio
import hashlib
import json
import logging

import pytest

from app.observability import (
    RequestLogMiddleware, _SafeJSONFormatter, bind_request, safe_request_id,
)


def test_request_id_and_username_are_safe() -> None:
    assert safe_request_id("req.good:1-2") == "req.good:1-2"
    assert safe_request_id("bad value").startswith("req_")
    assert safe_request_id("é").startswith("req_")
    scope = {}
    context = bind_request(scope, request_id="request-1", username="alice", agent_id="agent-code")
    assert context["username_hash"] == hashlib.sha256(b"alice").hexdigest()[:16]
    assert "username" not in context and "alice" not in repr(scope)


def test_formatter_drops_third_party_message_exception_and_extra() -> None:
    sentinel = "SECRET-token-header-body-binary"
    try:
        raise RuntimeError(sentinel)
    except RuntimeError:
        record = logging.LogRecord(
            "third.party", logging.ERROR, __file__, 1, sentinel, (), __import__("sys").exc_info()
        )
    record.headers = {"Authorization": sentinel}
    rendered = _SafeJSONFormatter().format(record)
    payload = json.loads(rendered)
    assert sentinel not in rendered
    assert payload == {
        "component": "third.party", "action": "log", "timestamp": payload["timestamp"],
        "level": "ERROR", "error_code": "RuntimeError",
    }


def test_middleware_sets_final_request_id_and_does_not_buffer_sse(monkeypatch) -> None:
    emitted = []
    monkeypatch.setattr("app.observability.emit", lambda action, **fields: emitted.append((action, fields)))
    first_sent = asyncio.Event()
    allow_second = asyncio.Event()

    async def app(scope, receive, send):
        bind_request(scope, request_id="final-id", username="alice")
        await send({"type": "http.response.start", "status": 200, "headers": [(b"x-cloud-request-id", b"old")]})
        await send({"type": "http.response.body", "body": b"data: first\n\n", "more_body": True})
        first_sent.set()
        await allow_second.wait()
        await send({"type": "http.response.body", "body": b"data: second\n\n", "more_body": False})

    sent = []

    async def send(message):
        sent.append(message)

    async def exercise():
        task = asyncio.create_task(RequestLogMiddleware(app)(
            {"type": "http", "headers": [(b"x-cloud-request-id", b"incoming")]}, lambda: None, send
        ))
        await asyncio.wait_for(first_sent.wait(), 1)
        assert len(sent) == 2 and sent[1]["body"] == b"data: first\n\n"
        assert not task.done()
        allow_second.set()
        await task

    asyncio.run(exercise())
    headers = sent[0]["headers"]
    assert [(name, value) for name, value in headers if name == b"x-cloud-request-id"] == [
        (b"x-cloud-request-id", b"final-id")
    ]
    assert emitted[0][0] == "http_request" and emitted[0][1]["status_code"] == 200
    assert "username" not in emitted[0][1]


def test_middleware_logs_failure_and_reraises(monkeypatch) -> None:
    emitted = []
    monkeypatch.setattr("app.observability.emit", lambda action, **fields: emitted.append((action, fields)))

    async def failed(scope, receive, send):
        raise ValueError("secret failure detail")

    with pytest.raises(ValueError, match="secret failure detail"):
        asyncio.run(RequestLogMiddleware(failed)(
            {"type": "http", "headers": []}, lambda: None, lambda message: None
        ))
    assert emitted[0][1]["status_code"] == 500
    assert emitted[0][1]["error_code"] == "ValueError"
