#!/usr/bin/env python3
"""Measure real OpenCode directly against the configured model gateway."""
import asyncio
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
INSTANCE = 'stage28-baseline'


async def main():
    spec = importlib.util.spec_from_file_location('load_client', ROOT / 'tests/load/run_load.py')
    load = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(load)
    output = ROOT / 'artifacts/perf'
    report = {'result': 'running', 'models': {}, 'scope': 'Direct warm OpenCode; real configured providers'}
    client = docker.from_env()
    with tempfile.TemporaryDirectory(prefix='cloud-stage28-') as tmp:
        directory = Path(tmp)
        shutil.copytree(ROOT / 'agents', directory / 'agents')
        config = load_config(ROOT / 'config.cfg')
        config = replace(config, platform=replace(config.platform, instance_id=INSTANCE))
        registry = Registry(directory / 'registry.db')
        registry.initialize()
        backend = LocalDockerBackend(config, registry, WorkspaceManager(directory / 'workspaces', directory / 'state', runtime_uid=10001, runtime_gid=10001), directory / 'agents', client=client)
        try:
            for agent, names in [('agent-code', ['coding-fast', 'coding-quality']), ('agent-data', ['data-fast', 'data-quality'])]:
                endpoint = await backend.acquire(agent, 'baseline')
                try:
                    for name in names:
                        summary = await load.run(endpoint.base_url, rounds=10, mode='opencode', matrix=[(agent, 'baseline', name)], output=output / f'direct-opencode-{name}')
                        report['models'][name] = summary
                        if summary['failures']:
                            raise RuntimeError(f'{name} has failed samples')
                finally:
                    await backend.release(endpoint)
            report['result'] = 'passed'
        except Exception as exc:
            report.update(result='failed', error=type(exc).__name__)
            raise
        finally:
            (output / 'direct-opencode-baseline.json').write_text(json.dumps(report, indent=2) + '\n')
            for container in client.containers.list(all=True, filters={'label': f'cloud.platform_instance={INSTANCE}'}):
                if container.labels.get('cloud.platform_instance') != INSTANCE:
                    raise RuntimeError('container ownership mismatch')
                container.remove(force=True)
            client.close()


if __name__ == '__main__':
    asyncio.run(main())
