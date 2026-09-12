import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.management import ManagementStore
from app.registry import Registry
from test_operations import service


def prepare(service, tmp_path):
    registry = Registry(tmp_path / 'routes.db')
    registry.initialize()
    service.backend.registry = registry
    roots = [tmp_path / 'workspaces', tmp_path / 'state']
    for root in roots:
        (root / 'agent-code').mkdir(parents=True)
        (root / 'agent-code' / 'history.txt').write_text('keep until confirmed')
        (root / 'agent-data').mkdir()
        (root / 'agent-data' / 'unrelated.txt').write_text('preserve')
    service.backend.workspaces = SimpleNamespace(workspace_root=roots[0], state_root=roots[1])
    registry.upsert_agent('agent-code', 'agent.cfg', 'image')
    registry.upsert_sandbox(sandbox_id='sbx_delete', agent_id='agent-code', username='alice',
        container_id=None, host_port=None, status='stopped', image_version='image')
    registry.record_session('ses_delete', 'sbx_delete', 'agent-code', 'alice', 'sessions/ses_delete')
    service.runtime.remove_sandboxes = AsyncMock()
    with service.store.edit() as data:
        data['agents']['agent-code']['lifecycle'] = 'archived'
    return roots


def test_confirmed_delete_preserves_other_agents_and_does_not_resurrect(service, tmp_path):
    roots = prepare(service, tmp_path)
    preview = service.deletion.preview('agent-code')
    assert preview['sessions'] == 1 and preview['files'] == 2
    impact = service.deletion.authorize('agent-code', preview['preview_id'], 'agent-code')
    jid, _ = service.submit('agent.delete', 'agent-code', 'delete-request', impact['revision'], impact['fingerprint'])
    asyncio.run(service.run(jid))
    data = service.store.read()[1]
    assert data['jobs'][jid]['status'] == 'succeeded'
    assert 'agent-code' not in data['agents'] and 'agent-code' in data['agent_tombstones']
    assert service.backend.registry.get_session_route('ses_delete') is None
    for root in roots:
        assert not (root / 'agent-code').exists()
        assert (root / 'agent-data' / 'unrelated.txt').read_text() == 'preserve'
    reopened = ManagementStore(service.store.root, service.store.agents_root)
    assert 'agent-code' not in reopened.read()[1]['agents']


def test_delete_rejects_changed_impact_and_wrong_confirmation(service, tmp_path):
    roots = prepare(service, tmp_path)
    preview = service.deletion.preview('agent-code')
    with pytest.raises(HTTPException):
        service.deletion.authorize('agent-code', preview['preview_id'], 'wrong')
    (roots[0] / 'agent-code' / 'new.txt').write_text('new output')
    with pytest.raises(HTTPException):
        service.deletion.authorize('agent-code', preview['preview_id'], 'agent-code')
    assert (roots[0] / 'agent-code' / 'history.txt').exists()


def test_delete_failure_keeps_agent_unavailable_and_retryable(service, tmp_path):
    prepare(service, tmp_path)
    impact = service.deletion.preview('agent-code')
    jid, _ = service.submit('agent.delete', 'agent-code', 'delete-request', impact['revision'], impact['fingerprint'])
    service.runtime.remove_sandboxes.side_effect = RuntimeError('Docker unavailable')
    asyncio.run(service.run(jid))
    assert service.store.read()[1]['agents']['agent-code']['lifecycle'] == 'deleting'
    with pytest.raises(HTTPException):
        service.submit('agent.restore', 'agent-code', 'restore-request')
    service.runtime.remove_sandboxes.side_effect = None
    impact = service.deletion.preview('agent-code')
    jid, _ = service.submit('agent.delete', 'agent-code', 'retry-request', impact['revision'], impact['fingerprint'])
    asyncio.run(service.run(jid))
    assert service.store.read()[1]['jobs'][jid]['status'] == 'succeeded'


def test_empty_catalog_does_not_bootstrap_again(service):
    with service.store.edit() as data:
        data['agents'] = {}
    reopened = ManagementStore(service.store.root, service.store.agents_root)
    assert reopened.read()[1]['agents'] == {}


def test_deleting_agent_cannot_publish_or_rollback(service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.admin_api import create_admin_router
    with service.store.edit() as data:
        data['agents']['agent-code']['lifecycle'] = 'deleting'
    app = FastAPI()
    app.include_router(create_admin_router(service.store, service.runtime))
    with TestClient(app) as client:
        for action in ('apply', 'rollback'):
            assert client.post('/cloud/admin/agents/agent-code/' + action, json={}).status_code == 409
