import asyncio
import socket
import tempfile
import unittest
from types import SimpleNamespace

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from admin_web.local_service.runtime import LocalServer, until_stopped
from admin_web.local_service.server import create_local_app


class LocalShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_iterator_closes_on_stop(self):
        stopping, closed = asyncio.Event(), asyncio.Event()

        async def source():
            try:
                yield b"first"
                await asyncio.Event().wait()
            finally:
                closed.set()

        stream = until_stopped(source(), stopping)
        self.assertEqual(await anext(stream), b"first")
        read = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        stopping.set()
        with self.assertRaises(StopAsyncIteration):
            await asyncio.wait_for(read, 1)
        self.assertTrue(closed.is_set())

    async def test_shutdown_ends_live_proxy_without_browser_disconnect(self):
        await self.proxy_case(True)

    async def test_browser_disconnect_closes_idle_upstream_without_shutdown(self):
        await self.proxy_case(False)

    async def proxy_case(self, shutdown):
        upstream = FastAPI()
        closed = asyncio.Event()

        @upstream.get("/event")
        async def event(request: Request):
            async def stream():
                try:
                    yield b"data: {}\n\n"
                    # Observe transport disconnect explicitly even with ASGI 2.4,
                    # whose idle StreamingResponse does not poll receive itself.
                    while not await request.is_disconnected():
                        await asyncio.sleep(0.01)
                finally:
                    closed.set()

            return StreamingResponse(stream(), media_type="text/event-stream")

        sockets, servers, tasks = [], [], []

        async def start(app, cls):
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            sockets.append(sock)
            server = cls(
                uvicorn.Config(app, log_level="error", timeout_graceful_shutdown=2)
            )
            servers.append(server)
            task = asyncio.create_task(server.serve(sockets=[sock]))
            tasks.append(task)
            async with asyncio.timeout(5):
                while not server.started:
                    if task.done():
                        await task
                    await asyncio.sleep(0.01)
            return server, task, f"http://127.0.0.1:{sock.getsockname()[1]}"

        try:
            _, _, upstream_url = await start(upstream, uvicorn.Server)
            with tempfile.TemporaryDirectory() as root:
                app = create_local_app(
                    root, SimpleNamespace(url=upstream_url, token="test")
                )
                server, task, url = await start(app, LocalServer)
                async with httpx.AsyncClient(trust_env=False) as client:
                    async with client.stream("GET", url + "/remote/event") as response:
                        self.assertEqual(response.status_code, 200)
                        chunks = response.aiter_raw()
                        self.assertIn(b"data:", await anext(chunks))
                        if shutdown:
                            server.should_exit = True
                            # Browser keeps the stream open throughout server shutdown.
                            await asyncio.wait_for(asyncio.shield(task), 1.5)
                            with self.assertRaises(StopAsyncIteration):
                                await anext(chunks)
                    await asyncio.wait_for(closed.wait(), 1)
                    self.assertEqual(app.state.stopping.is_set(), shutdown)
        finally:
            for server in servers:
                server.should_exit = True
            await asyncio.wait_for(asyncio.gather(*tasks), 5)
            for sock in sockets:
                sock.close()


if __name__ == "__main__":
    unittest.main()
