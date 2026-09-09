#!/usr/bin/env python3
"""Verify default-authorized tools complete without pending permission requests."""
import asyncio
import argparse
import importlib.util
import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

import docker
import httpx
from app.config import load_config
from app.registry import Registry
from app.sandbox import LocalDockerBackend
from app.workspace import WorkspaceManager

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = 'permission-diagnosis'


async def main(external_directory=False):
    spec = importlib.util.spec_from_file_location('load_client', ROOT / 'tests/load/run_load.py')
    load = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(load)
    output = ROOT / 'artifacts/perf'
    report = {'result': 'running', 'models': {}, 'scope': 'Default tool authorization; actual bash completion without approval'}
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
            endpoint = await backend.acquire('agent-data', 'diagnostic')
            async with httpx.AsyncClient(base_url=endpoint.base_url, timeout=60, trust_env=False) as http:
                session = (await http.post('/session', json={'title': 'permission diagnosis'})).json()['id']
                prompt = asyncio.create_task(http.post('/session/'+session+'/message', json={'model': {'providerID': 'cloud-model-gateway', 'modelID': 'data-fast'}, 'parts': [{'type':'text','text':('Use the bash tool to execute exactly: cat /etc/os-release . Do not answer from memory. Then reply OK.' if external_directory else 'Use the bash tool to run: ls /opt/agent/skills/ && cat /opt/agent/agent.cfg . Then reply OK.')}]}))
                try:
                    for _ in range(100):
                        response = await http.get('/permission')
                        response.raise_for_status()
                        pending = response.json()
                        if pending:
                            report['pending_permissions'] = pending
                            break
                        if prompt.done():
                            completed = await prompt
                            completed.raise_for_status()
                            assert not completed.json().get('info', {}).get('error')
                            report['message_http_status'] = completed.status_code
                            report['tools'] = [{'tool': p.get('tool'), 'status': p.get('state', {}).get('status'), 'input': p.get('state', {}).get('input')} for m in (await http.get('/session/'+session+'/message')).json() for p in m.get('parts', []) if p.get('type') == 'tool']
                            break
                        await asyncio.sleep(0.5)
                    else:
                        report['observation'] = 'no permission observed within 50 seconds'
                finally:
                    await http.post('/session/'+session+'/abort')
                    prompt.cancel()
                    try:
                        await prompt
                    except asyncio.CancelledError:
                        pass
            await backend.release(endpoint)
            assert report.get('message_http_status') == 200 and not report.get('pending_permissions'), report
            expected_path = '/etc/os-release' if external_directory else '/opt/agent'
            assert any(t['tool'] == 'bash' and t['status'] == 'completed' and expected_path in (t.get('input') or {}).get('command', '') for t in report.get('tools', [])), report
            report['result'] = 'passed'
        except Exception as exc:
            report.update(result='failed', error=type(exc).__name__)
            raise
        finally:
            (output / ('permission-default-external.json' if external_directory else 'permission-default-agent.json')).write_text(json.dumps(report, indent=2) + '\n')
            for container in client.containers.list(all=True, filters={'label': f'cloud.platform_instance={INSTANCE}'}):
                if container.labels.get('cloud.platform_instance') != INSTANCE:
                    raise RuntimeError('container ownership mismatch')
                container.remove(force=True)
            client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--external-directory", action="store_true")
    asyncio.run(main(parser.parse_args().external_directory))
