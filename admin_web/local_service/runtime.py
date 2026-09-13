"""Bounded local shutdown, including otherwise unbounded SSE responses."""

import asyncio

import uvicorn


async def until_stopped(source, stopping):
    iterator = source.__aiter__()
    stop = asyncio.create_task(stopping.wait())
    pending = None
    try:
        while not stopping.is_set():
            pending = asyncio.create_task(anext(iterator))
            done, _ = await asyncio.wait(
                (pending, stop), return_when=asyncio.FIRST_COMPLETED
            )
            if stop in done:
                break
            try:
                yield pending.result()
            except StopAsyncIteration:
                break
    finally:
        tasks = [task for task in (pending, stop) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await iterator.aclose()


class LocalServer(uvicorn.Server):
    async def shutdown(self, sockets=None):
        # Lifespan shutdown runs AFTER Uvicorn drains requests, so notify streams
        # here; doing this only in lifespan would deadlock on an idle SSE stream.
        self.config.app.state.stopping.set()
        await super().shutdown(sockets)
