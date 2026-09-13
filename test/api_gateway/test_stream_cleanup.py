import asyncio

from api_gateway.main import _ClosingStreamingResponse


def scope():
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/event",
        "raw_path": b"/event",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
        "root_path": "",
    }


class Upstream:
    def __init__(self, gate=None):
        self.gate = gate
        self.close_calls = 0
        self.closed = asyncio.Event()

    async def aiter_raw(self):
        yield b"data: first\n\n"
        if self.gate is None:
            await asyncio.Event().wait()
        else:
            await self.gate.wait()
            yield b"data: second\n\n"

    async def aclose(self):
        self.close_calls += 1
        # Cancellation here used to interrupt cleanup and leak the connection.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.closed.set()


async def never_disconnect():
    await asyncio.Event().wait()


def test_asgi_disconnect_completes_upstream_close_once():
    async def exercise():
        upstream = Upstream()
        first = asyncio.Event()
        disconnect = asyncio.Event()

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                first.set()
                disconnect.set()

        async def receive():
            await disconnect.wait()
            return {"type": "http.disconnect"}

        response = _ClosingStreamingResponse(upstream, status_code=200)
        task = asyncio.create_task(response(scope(), receive, send))
        await asyncio.wait_for(first.wait(), 1)
        await asyncio.wait_for(task, 1)

        assert upstream.closed.is_set()
        assert upstream.close_calls == 1

    asyncio.run(exercise())


def test_normal_stream_is_not_closed_before_last_chunk():
    async def exercise():
        gate = asyncio.Event()
        upstream = Upstream(gate)
        bodies = []
        first = asyncio.Event()

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                bodies.append(message["body"])
                first.set()

        response = _ClosingStreamingResponse(upstream, status_code=200)
        task = asyncio.create_task(response(scope(), never_disconnect, send))
        await asyncio.wait_for(first.wait(), 1)
        assert not upstream.closed.is_set()
        gate.set()
        await asyncio.wait_for(task, 1)

        assert bodies == [b"data: first\n\n", b"data: second\n\n"]
        assert upstream.closed.is_set()
        assert upstream.close_calls == 1

    asyncio.run(exercise())
