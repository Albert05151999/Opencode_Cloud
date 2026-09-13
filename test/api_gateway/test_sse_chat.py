import asyncio
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "sse_chat", Path(__file__).resolve().parents[2] / "api_gateway/tools/sse_chat.py"
)
chat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chat)


def test_display_filters_user_and_deduplicates_snapshot(capsys):
    display = chat.Display("ses_a")
    display.accept(
        {
            "type": "message.updated",
            "properties": {
                "info": {"sessionID": "ses_a", "id": "msg_a", "role": "assistant"}
            },
        }
    )
    display.accept(
        {
            "type": "message.part.delta",
            "properties": {
                "sessionID": "ses_other",
                "messageID": "msg_a",
                "partID": "p",
                "field": "text",
                "delta": "secret",
            },
        }
    )
    display.accept(
        {
            "type": "message.part.delta",
            "properties": {
                "sessionID": "ses_a",
                "messageID": "msg_a",
                "partID": "p",
                "field": "text",
                "delta": "Hello",
            },
        }
    )
    display.accept(
        {
            "type": "message.part.updated",
            "properties": {
                "part": {
                    "sessionID": "ses_a",
                    "messageID": "msg_a",
                    "id": "p",
                    "type": "text",
                    "text": "Hello world",
                }
            },
        }
    )
    assert capsys.readouterr().out == "Hello world"


def test_initial_idle_does_not_complete_turn():
    display = chat.Display("ses_a")
    event = lambda status: {
        "type": "session.status",
        "properties": {"sessionID": "ses_a", "status": {"type": status}},
    }
    assert not display.accept(event("idle"))
    assert not display.accept(event("busy"))
    assert display.accept(event("idle"))


def test_sse_multiline_and_comments():
    class Response:
        async def aiter_lines(self):
            for line in [
                ": keepalive",
                'data: {"type":',
                'data: "server.connected"}',
                "",
            ]:
                yield line

    async def run():
        return [item async for item in chat.events(Response())]

    assert asyncio.run(run()) == [{"type": "server.connected"}]
