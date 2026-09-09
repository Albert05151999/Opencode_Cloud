#!/usr/bin/env python3
"""Attribute real native HTTP latency per request, excluding acquire and upstream I/O."""
import asyncio
import csv
import json
import math
import shutil
import socket
import tempfile
import time
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import replace
from pathlib import Path

import httpx
import uvicorn
from app.config import load_config
from app.main import build_app
from app.gateway import SessionRecorder

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = 'native-overhead-verification'
measurement = ContextVar('native_measurement', default=None)


async def main():
    output = ROOT / 'artifacts/perf/native-overhead' / time.strftime('run-%Y%m%d-%H%M%S')
    output.mkdir(parents=True)
    report = {'result': 'running', 'scope': 'Real HTTP, 20 eight-way rounds; per-request client elapsed minus server acquire and complete upstream stream; no model calls', 'requests': []}
    with tempfile.TemporaryDirectory(prefix='cloud-native-overhead-') as tmp:
        root = Path(tmp)
        shutil.copytree(ROOT / 'agents', root / 'agents')
        config = load_config(ROOT / 'config.cfg')
        config = replace(config, platform=replace(config.platform, instance_id=INSTANCE, data_root=str(root)), storage=replace(config.storage, workspace_root=str(root / 'workspaces'), state_root=str(root / 'state')))
        app = build_app(config, root / 'agents')
        backend = app.state.backend
        original_record = SessionRecorder.record
        original_batch = backend.registry.record_sessions_batch
        report['session_batches'] = []

        async def recorded(self, *entry):
            started = time.perf_counter()
            try:
                return await original_record(self, *entry)
            finally:
                current = measurement.get()
                if current is not None:
                    current['record_ms'] = (time.perf_counter() - started) * 1000

        def batch(entries):
            started = time.perf_counter()
            try:
                return original_batch(entries)
            finally:
                report['session_batches'].append({'size': len(entries), 'duration_ms': (time.perf_counter() - started) * 1000})

        SessionRecorder.record = recorded
        backend.registry.record_sessions_batch = batch
        upstream = app.state.health_monitor.client
        original_acquire, original_stream = backend.acquire, upstream.stream
        original_release = backend.release
        original_connect = backend.registry.connect
        observations = {}
        client_starts = {}

        @contextmanager
        def connect():
            current = measurement.get()
            track = current is not None and current.get('releasing', False)
            started = time.perf_counter()
            with original_connect() as connection:
                entered = time.perf_counter()
                try:
                    yield connection
                finally:
                    body_end = time.perf_counter()
            if track:
                current['release_connect_ms'] += (entered - started) * 1000
                current['release_sql_ms'] += (body_end - entered) * 1000
                current['release_commit_close_ms'] += (time.perf_counter() - body_end) * 1000

        backend.registry.connect = connect

        async def acquire(*args, **kwargs):
            started = time.perf_counter()
            try:
                return await original_acquire(*args, **kwargs)
            finally:
                current = measurement.get()
                if current is not None:
                    current['acquire_ms'] += (time.perf_counter() - started) * 1000

        async def release(endpoint, **kwargs):
            started = time.perf_counter()
            current = measurement.get()
            if current is not None:
                current['releasing'] = True
            try:
                return await original_release(endpoint, **kwargs)
            finally:
                current = measurement.get()
                if current is not None:
                    current['release_ms'] += (time.perf_counter() - started) * 1000
                    current['releasing'] = False

        @asynccontextmanager
        async def stream(*args, **kwargs):
            started = time.perf_counter()
            try:
                async with original_stream(*args, **kwargs) as response:
                    yield response
            finally:
                current = measurement.get()
                if current is not None:
                    current['upstream_ms'] += (time.perf_counter() - started) * 1000

        async def instrumented(scope, receive, send):
            request_id = dict(scope.get('headers', [])).get(b'x-cloud-request-id')
            if scope['type'] != 'http' or request_id is None:
                return await app(scope, receive, send)
            current = dict.fromkeys(('acquire_ms', 'upstream_ms', 'release_ms', 'release_connect_ms', 'release_sql_ms', 'release_commit_close_ms', 'record_ms'), 0.0)
            token = measurement.set(current)
            started = time.perf_counter()
            current['ingress_ms'] = (started - client_starts[request_id.decode()]) * 1000
            try:
                await app(scope, receive, send)
            finally:
                current['server_ms'] = (time.perf_counter() - started) * 1000
                observations[request_id.decode()] = current
                measurement.reset(token)

        backend.acquire, upstream.stream = acquire, stream
        backend.release = release
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        listener.bind(('127.0.0.1', 0))
        server = uvicorn.Server(uvicorn.Config(instrumented, log_level='warning'))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(15):
                while not server.started:
                    if task.done():
                        await task
                    await asyncio.sleep(0.05)
            matrix = [(agent, user) for agent in ('agent-code', 'agent-data') for user in ('overhead-alice', 'overhead-bob')]
            for agent, user in matrix:
                endpoint = await backend.acquire(agent, user)
                await backend.release(endpoint)
            async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{listener.getsockname()[1]}', trust_env=False, timeout=30) as client:
                sessions = {}
                for agent, user in matrix:
                    response = await client.post('/session', headers={'X-Cloud-Agent-ID': agent, 'X-Cloud-Username': user}, json={'title': 'overhead seed'})
                    response.raise_for_status()
                    sessions[(agent, user)] = response.json()['id']
                async def request(index, agent, user):
                    request_id = f'overhead-{index}'
                    operation = (index // 8) % 4
                    path = ['/global/health', '/session', '/session', '/session/' + sessions[(agent, user)]][operation]
                    method = 'POST' if operation == 2 else 'GET'
                    started = time.perf_counter()
                    client_starts[request_id] = started
                    response = await client.request(method, path, headers={'X-Cloud-Agent-ID': agent, 'X-Cloud-Username': user, 'X-Cloud-Request-ID': request_id}, **({'json': {'title': request_id}} if method == 'POST' else {}))
                    total = (time.perf_counter() - started) * 1000
                    response.raise_for_status()
                    if path == '/global/health':
                        assert response.json()['healthy'] is True
                    elif operation == 1:
                        assert isinstance(response.json(), list)
                    else:
                        assert response.json()['id'].startswith('ses_')
                    async with asyncio.timeout(5):
                        while request_id not in observations:
                            await asyncio.sleep(0)
                    timing = observations.pop(request_id)
                    assert timing['acquire_ms'] > 0 and timing['upstream_ms'] > 0
                    residual = total - timing['acquire_ms'] - timing['upstream_ms']
                    assert residual >= 0, 'invalid timing attribution'
                    report['requests'].append({'request_id': request_id, 'path': path, 'operation': ['health', 'list_sessions', 'create_session', 'get_session'][operation], 'total_ms': total, **timing, 'overhead_ms': residual})
                for round_id in range(20):
                    await asyncio.gather(*(request(round_id * 8 + index, *owner) for index, owner in enumerate(matrix * 2)))
            values = sorted(row['overhead_ms'] for row in report['requests'])
            report['overhead_ms'] = {'count': len(values), 'p50': values[math.ceil(len(values) * .5) - 1], 'p95': values[math.ceil(len(values) * .95) - 1]}
            report['leases_after_requests'] = sum(backend.in_use.values())
            report['operations_p95_ms'] = {operation: sorted(row['overhead_ms'] for row in report['requests'] if row['operation'] == operation)[37] for operation in ('health', 'list_sessions', 'create_session', 'get_session')}
            assert not backend.in_use
            assert report['overhead_ms']['p95'] <= 100, report['overhead_ms']
            assert all(value <= 100 for value in report['operations_p95_ms'].values()), report['operations_p95_ms']
            report['result'] = 'passed'
        except Exception as exc:
            report.update(result='failed', error=type(exc).__name__)
            raise
        finally:
            (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            if report['requests']:
                with (output / 'requests.csv').open('w', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(report['requests'][0]))
                    writer.writeheader()
                    writer.writerows(report['requests'])
            (output / 'controller.prom').write_bytes(app.state.metrics.render())
            for container in backend.client.containers.list(all=True, filters={'label': f'cloud.platform_instance={INSTANCE}'}):
                assert container.labels.get('cloud.platform_instance') == INSTANCE
                container.remove(force=True)
            server.should_exit = True
            await task
            listener.close()
    print(json.dumps({key: value for key, value in report.items() if key != 'requests'}), flush=True)


if __name__ == '__main__':
    # Match the Linux production CLI (uvicorn[standard], loop=auto).
    import uvloop
    uvloop.run(main())
