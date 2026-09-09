import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("run_load", Path(__file__).resolve().parents[1] / "load/run_load.py")
load = importlib.util.module_from_spec(spec)
spec.loader.exec_module(load)


def test_ttft_ignores_connection_user_content_and_other_sessions():
    observer = load.AssistantTokenObserver("ses_test")
    assert not observer.observe({"type": "server.connected"})
    assert not observer.observe({"type": "message.updated", "properties": {"sessionID": "ses_test", "info": {"id": "msg_user", "role": "user"}}})
    assert not observer.observe({"type": "message.part.updated", "properties": {"sessionID": "ses_test", "part": {"messageID": "msg_user", "type": "text", "text": "user input"}}})
    observer.observe({"type": "message.updated", "properties": {"sessionID": "ses_test", "info": {"id": "msg_assistant", "role": "assistant"}}})
    event = {"type": "message.part.delta", "properties": {"sessionID": "ses_other", "messageID": "msg_assistant", "field": "text", "delta": "token"}}
    assert not observer.observe(event)
    event["properties"]["sessionID"] = "ses_test"
    assert observer.observe(event)


def test_percentiles_use_nearest_rank_and_handle_empty_samples():
    assert load.percentile([], 0.95) is None
    assert load.percentile([4, 1, 2, 3], 0.5) == 2
    assert load.percentile([4, 1, 2, 3], 0.95) == 4


def test_timeout_after_first_token_preserves_ttft(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager

    class Response:
        def raise_for_status(self):
            pass

    class Client:
        @asynccontextmanager
        async def stream(self, *args, **kwargs):
            yield Response()

    async def events(response):
        yield {"choices": [{"delta": {"content": "first"}}]}
        raise TimeoutError("completion stalled after content")

    monkeypatch.setattr(load, "sse_events", events)
    result = asyncio.run(load.one_request(Client(), "agent-code", "alice", "coding-fast", mode="model"))
    assert result["status"] == "failed"
    assert result["error"] == "TimeoutError"
    assert result["first_token_at"] is not None
    assert result["ttft_ms"] >= 0
    assert result["request_ttft_ms"] >= result["ttft_ms"]
