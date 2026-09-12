"""Two real users against an existing Agent in an isolated controller instance."""
import asyncio
import configparser
import json
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from app.config import load_config
from app.main import build_app


async def main():
    root = Path(tempfile.mkdtemp(prefix='cloud-load-check-', dir='/srv'))
    root.chmod(0o755)
    shutil.copytree(ROOT / 'agents', root / 'agents')
    config = configparser.ConfigParser(interpolation=None)
    config.read(ROOT / 'config.cfg')
    instance = 'loadcheck-' + secrets.token_hex(6)
    config['platform'].update(instance_id=instance, host='127.0.0.1', data_root=str(root / 'data'))
    config['storage'].update(workspace_root=str(root / 'workspaces'), state_root=str(root / 'state'))
    (root / 'data').mkdir()
    token = secrets.token_urlsafe(40)
    (root / 'data/admin-token').write_text(token)
    with (root / 'config.cfg').open('w') as stream:
        config.write(stream)
    app = build_app(load_config(root / 'config.cfg', environ={}), root / 'agents')
    report = {'result': 'failed', 'instance': instance, 'checks': []}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test',
                headers={'Authorization': 'Bearer ' + token}) as api:
            backend = app.state.backend
            try:
                options = (await api.get('/cloud/admin/load-tests/options')).json()
                assert any(a['id'] == 'agent-code' for a in options['agents'])
                capacity = (await api.get('/cloud/admin/load-tests/capacity')).json()
                assert capacity['known'], capacity
                report['capacity'] = capacity
                oversized = await api.post('/cloud/admin/load-tests', json={'request_id': secrets.token_hex(16),
                    'agents': [{'agent_id': 'agent-code', 'users': 100, 'cpu_limit': 64, 'memory_mb': 65536}]})
                assert oversized.status_code == 409
                assert (await api.get('/cloud/admin/load-tests')).json()['total'] == 0
                report['checks'].append('live host and quota sampling; over-budget request rejected without test users')
                catalog = app.state.management.store.read()
                ordinary = backend.workspaces.ensure_user_layout('agent-code', 'ordinary-user').workspace / 'keep.txt'
                ordinary.write_text('normal user data')
                payload = {'request_id': secrets.token_hex(16), 'agents': [
                    {'agent_id': 'agent-code', 'users': 2, 'cpu_limit': 1, 'memory_mb': 1024}], 'timeout_seconds': 300}
                response = await api.post('/cloud/admin/load-tests', json=payload)
                assert response.status_code == 202, response.text
                rid = response.json()['id']
                assert (await api.post('/cloud/admin/load-tests', json=payload)).json() == {'id': rid, 'created': False}
                for _ in range(480):
                    value = (await api.get('/cloud/admin/load-tests/' + rid)).json()
                    if value['status'] not in {'queued', 'preparing', 'running', 'cancelling'}:
                        break
                    await asyncio.sleep(1)
                report['run'] = value
                assert value['status'] == 'completed', value['summary']
                assert len(value['capacity_checks']) >= 2
                assert value['summary']['succeeded'] == value['summary']['submitted'] == 2
                assert len({u['sandbox_id'] for u in value['users']}) == 2
                report['checks'].append('two mock users, independent sandboxes, one concurrent fixed request each')
                for user in value['users']:
                    record = backend.registry.get_sandbox(user['agent_id'], user['username'])
                    container = await backend._get_container(record.container_id)
                    assert container.attrs['HostConfig']['NanoCpus'] == 1_000_000_000
                    assert container.attrs['HostConfig']['Memory'] == 1024**3
                    assert container.attrs['Config']['Labels']['cloud.load_test'] == rid
                assert app.state.management.store.read() == catalog
                report['checks'].append('Docker resource limits verified; Agent catalog unchanged')
                assert (await api.get(f'/cloud/admin/load-tests/{rid}/report?format=csv')).status_code == 200
                await api.post(f'/cloud/admin/load-tests/{rid}/cleanup', json={'confirmation': rid})
                for _ in range(120):
                    cleaned = (await api.get('/cloud/admin/load-tests/' + rid)).json()
                    if cleaned['cleanup_status'] != 'cleaning':
                        break
                    await asyncio.sleep(1)
                assert cleaned['cleanup_status'] == 'cleaned', cleaned
                assert ordinary.read_text() == 'normal user data'
                for user in value['users']:
                    assert backend.registry.get_sandbox(user['agent_id'], user['username']) is None
                    assert not (root / 'workspaces' / user['agent_id'] / user['username']).exists()
                    denied = await api.post('/session', json={'_cloud': {'agent_id': user['agent_id'], 'username': user['username']}})
                    assert denied.status_code == 409
                assert (await api.get('/cloud/admin/load-tests/' + rid)).json()['summary'] == value['summary']
                report['checks'].append('explicit cleanup removes only test data, blocks resurrection, and retains report')
                report['result'] = 'passed'
            finally:
                await app.state.management.close()
                owned = await asyncio.to_thread(backend.client.containers.list, all=True,
                    filters={'label': 'cloud.platform_instance=' + instance})
                for container in owned:
                    await asyncio.to_thread(container.remove, force=True)
                destination = ROOT / 'artifacts/web/load-testing-verification.json'
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != 'run'}, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
