"""Real Docker operations checks without requiring a provider completion."""
import asyncio
import configparser
import copy
import json
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from app.main import build_app
from app.config import load_config


async def main():
    root = Path(tempfile.mkdtemp(prefix='cloud-operations-', dir='/srv'))
    root.chmod(0o755)
    shutil.copytree(ROOT / 'agents', root / 'agents')
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(ROOT / 'config.cfg')
    instance = 'optest-' + secrets.token_hex(5)
    cfg['platform'].update(instance_id=instance, host='127.0.0.1', data_root=str(root / 'data'))
    cfg['storage'].update(workspace_root=str(root / 'workspaces'), state_root=str(root / 'state'))
    (root / 'data').mkdir()
    token = secrets.token_urlsafe(40)
    (root / 'data/admin-token').write_text(token)
    with (root / 'config.cfg').open('w') as f:
        cfg.write(f)
    app = build_app(load_config(root / 'config.cfg', environ={}), root / 'agents')
    report = {'instance': instance, 'checks': [], 'result': 'failed'}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test',
                headers={'Authorization': 'Bearer ' + token}, timeout=180) as client:
            async def api(method, path, **kwargs):
                response = await client.request(method, path, **kwargs)
                assert response.is_success, (path, response.status_code, response.text[:300])
                return response.json()
            async def operation(path, payload=None):
                payload = {'request_id': secrets.token_hex(16)} if payload is None else payload
                job = await api('POST', path, json=payload)
                if 'request_id' in payload:
                    assert await api('POST', path, json=payload) == job
                for _ in range(180):
                    status = await api('GET', '/cloud/admin/jobs/' + job['job_id'])
                    if status['status'] in {'failed', 'succeeded'}:
                        assert status['status'] == 'succeeded', status
                        report['checks'].append(path)
                        return
                    await asyncio.sleep(1)
                raise RuntimeError('Operation timeout')
            try:
                catalog = await api('GET', '/cloud/admin/catalog')
                config = copy.deepcopy(catalog['agents']['agent-code']['draft'])
                config['bindings'] = []
                await api('PUT', '/cloud/admin/agents/verify-operations', json={'config': config})
                await operation('/cloud/admin/agents/verify-operations/apply', {})
                session = await api('POST', '/session', json={'_cloud': {'agent_id': 'verify-operations', 'username': 'tester'}})
                sid = session['id']
                marker = root / 'workspaces/verify-operations/tester/preserved.txt'
                marker.write_text('history must survive restart')
                sandbox = (await api('GET', '/cloud/admin/sandboxes?q=verify-operations'))['items'][0]['sandbox_id']
                for action in ('restart', 'stop', 'start'):
                    await operation('/cloud/admin/sandboxes/' + sandbox + '/' + action)
                    assert marker.read_text() == 'history must survive restart'
                assert (await api('GET', '/session/' + sid))['id'] == sid
                package = await client.get('/cloud/admin/exports/resources')
                preview = await api('POST','/cloud/admin/imports/preview',files={'file':('resources.json',package.content)})
                choices = [{'key':i['key'],'target_id':i['id']+'-copy','replace':False} for i in preview['items'] if not i.get('error')]
                imported = await api('POST','/cloud/admin/imports/'+preview['preview_id']+'/commit',json={'selections':choices})
                assert imported['published'] is False and imported['assigned_agents']==[]
                templates = await api('GET','/cloud/admin/agent-templates')
                template = next(t for t in templates if t['source_id']=='verify-operations-draft')
                await api('POST','/cloud/admin/agent-templates/'+template['id']+'/restore',json={'agent_id':'restored-operations'})
                await operation('/cloud/admin/agents/restored-operations/apply',{})
                restored = await api('POST','/session',json={'_cloud':{'agent_id':'restored-operations','username':'tester'}})
                assert restored['id']!=sid
                native = await client.get('/cloud/admin/exports/native/verify-operations')
                assert native.is_success
                native_preview = await api('POST','/cloud/admin/imports/preview',files={'file':('opencode.zip',native.content)})
                assert native_preview['items']
                report['checks'].append('platform migration restores an unpublished Agent template and native package imports')
                operations = app.state.management.operations
                record = operations.find(sandbox)
                assert await operations.recovery.idle_evidence(record)
                policy = operations.recovery.policy()
                policy.failure_threshold = 1
                operations.recovery.save_policy(policy)
                container = await app.state.backend._get_container(record.container_id)
                app.state.backend._verify_ownership(container, record.agent_id, record.username)
                await asyncio.to_thread(container.stop, timeout=10)
                app.state.backend.registry.set_health_status(sandbox, 'unhealthy')
                await operations.recovery.tick(dependencies_healthy=True)
                for _ in range(180):
                    jobs = [job for job in operations.store.read()[1]['jobs'].values() if job['kind'] == 'sandbox.recover']
                    if jobs and jobs[-1]['status'] in {'failed', 'succeeded'}:
                        assert jobs[-1]['status'] == 'succeeded', jobs[-1]
                        break
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError('Automatic recovery timeout')
                assert marker.read_text() == 'history must survive restart'
                report['checks'].append('idle sandbox automatic recovery preserves workspace')
                for action in ('archive', 'restore', 'archive'):
                    await operation('/cloud/admin/agents/verify-operations/' + action)
                impact = await api('GET', '/cloud/admin/agents/verify-operations/delete-preview')
                assert impact['sessions'] == 1 and impact['files'] > 0
                await operation('/cloud/admin/agents/verify-operations/delete', {'request_id': secrets.token_hex(16),
                    'preview_id': impact['preview_id'], 'confirmation': 'verify-operations'})
                assert not marker.exists()
                assert 'agent-code' in (await api('GET', '/cloud/admin/catalog'))['agents']
                report['result'] = 'passed'
            finally:
                for container in app.state.backend.client.containers.list(all=True, filters={'label': 'cloud.platform_instance=' + instance}):
                    container.remove(force=True)
                output = ROOT / 'artifacts/web/operations-verification.json'
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
