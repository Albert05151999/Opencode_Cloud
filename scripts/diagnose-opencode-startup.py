#!/usr/bin/env python3
"""Measure real OpenCode directly against the configured model gateway."""
import asyncio
import contextvars
import time
import importlib.util
import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

import docker
from app.config import load_config
from app.registry import Registry
from app.sandbox import LocalDockerBackend
from app.workspace import WorkspaceManager

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = 'stage29-acquire-profile'


async def main():
    spec = importlib.util.spec_from_file_location('load_client', ROOT / 'tests/load/run_load.py')
    load = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(load)
    output = ROOT / 'artifacts/perf'
    report = {'result': 'running', 'samples': [], 'scope': 'Eight-way acquire profiling without model requests'}
    client = docker.from_env()
    with tempfile.TemporaryDirectory(prefix='cloud-stage28-') as tmp:
        directory = Path(tmp)
        shutil.copytree(ROOT / 'agents', directory / 'agents')
        config = load_config(ROOT / 'config.cfg')
        config = replace(config, platform=replace(config.platform, instance_id=INSTANCE))
        registry = Registry(directory / 'registry.db')
        registry.initialize()
        backend = LocalDockerBackend(config, registry, WorkspaceManager(directory / 'workspaces', directory / 'state', runtime_uid=10001, runtime_gid=10001), directory / 'agents', client=client)
        current = contextvars.ContextVar('profile_sample')
        def wrap_sync(obj, name):
            original = getattr(obj, name)
            def wrapped(*args, **kwargs):
                started = time.perf_counter()
                try:
                    return original(*args, **kwargs)
                finally:
                    record = current.get(None)
                    if record is not None:
                        record['steps'].setdefault(name, []).append((time.perf_counter()-started)*1000)
            setattr(obj, name, wrapped)
        def wrap_async(name):
            original = getattr(backend, name)
            async def wrapped(*args, **kwargs):
                started = time.perf_counter()
                try:
                    return await original(*args, **kwargs)
                finally:
                    current.get()['steps'].setdefault(name, []).append((time.perf_counter()-started)*1000)
            setattr(backend, name, wrapped)
        for name in ['_agent_path']:
            wrap_sync(backend, name)
        wrap_sync(backend.workspaces, 'ensure_user_layout')
        for name in ['upsert_agent', 'get_sandbox', 'upsert_sandbox']:
            wrap_sync(registry, name)
        for name in ['_find_existing', '_create_container', '_start_container', '_wait_ready', '_health_probe', '_persist', '_acquire_locked']:
            wrap_async(name)
        async def sample(agent, user, phase):
            record = {'phase': phase, 'steps': {}}
            token = current.set(record)
            started = time.perf_counter()
            try:
                endpoint = await backend.acquire(agent, user)
                record['total_ms'] = (time.perf_counter()-started)*1000
                record['reused'] = endpoint.reused
                await backend.release(endpoint)
            finally:
                report['samples'].append(record)
                current.reset(token)
        try:
            for index in range(2):
                await asyncio.gather(*(sample(agent, user, 'fresh' if index == 0 else 'recreated') for agent in ['agent-code', 'agent-data'] for user in ['profile-alice', 'profile-bob'] for _ in range(2)))
                containers = client.containers.list(all=True, filters={'label': f'cloud.platform_instance={INSTANCE}'})
                report.setdefault('containers', []).append([{'phase': index, 'logs': c.logs(timestamps=True).decode(errors='replace'), 'cpu': c.stats(stream=False).get('cpu_stats', {}).get('throttling_data', {}), 'started_at': c.attrs['State']['StartedAt']} for c in containers])
                for c in containers:
                    c.remove(force=True)
            report['result'] = 'passed' 
        except Exception as exc:
            report.update(result='failed', error=type(exc).__name__)
            raise
        finally:
            (output / 'startup-diagnosis.json').write_text(json.dumps(report, indent=2) + '\n')
            for container in client.containers.list(all=True, filters={'label': f'cloud.platform_instance={INSTANCE}'}):
                if container.labels.get('cloud.platform_instance') != INSTANCE:
                    raise RuntimeError('container ownership mismatch')
                container.remove(force=True)
            client.close()


if __name__ == '__main__':
    asyncio.run(main())
