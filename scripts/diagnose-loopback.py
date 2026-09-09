"""Compare a default-protocol test socket with an explicit TCP listener."""
import asyncio
import json
import socket
import time
from pathlib import Path

import httpx
import uvicorn
from uvicorn.protocols.http.httptools_impl import HttpToolsProtocol
from app.main import create_app


async def measure(protocol):
    options, durations = [], []

    class Protocol(HttpToolsProtocol):
        def connection_made(self, transport):
            super().connection_made(transport)
            connection = transport.get_extra_info('socket')
            options.append(connection.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY))

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM, protocol)
    listener.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(create_app(), log_level='warning', http=Protocol))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(.01)
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{listener.getsockname()[1]}', trust_env=False) as client:
            async def request():
                started = time.perf_counter()
                response = await client.get('/cloud/health')
                response.raise_for_status()
                durations.append((time.perf_counter() - started) * 1000)
            for _ in range(20):
                await asyncio.gather(*(request() for _ in range(8)))
    finally:
        server.should_exit = True
        await task
        listener.close()
    return {'protocol': protocol, 'accepted_socket_nodelay': options, 'samples_ms': durations, 'p50_ms': sorted(durations)[79], 'p95_ms': sorted(durations)[151]}


async def main():
    before, after = await measure(0), await measure(socket.IPPROTO_TCP)
    assert after['accepted_socket_nodelay'] and all(after['accepted_socket_nodelay'])
    report = {'result': 'passed', 'before': before, 'after': after, 'scope': 'No Docker or database; 20 eight-way rounds per listener protocol'}
    output = Path(__file__).resolve().parents[1] / 'artifacts/perf/loopback-diagnosis.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': 'passed', 'before_p95_ms': before['p95_ms'], 'after_p95_ms': after['p95_ms']}))


if __name__ == '__main__':
    asyncio.run(main())
