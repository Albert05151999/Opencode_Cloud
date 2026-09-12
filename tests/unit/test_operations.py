import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.management import ManagementStore
from app.operations import Operations
from app.operations_api import create_operations_router
from app.registry import SandboxRecord

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def service(tmp_path):
    store = ManagementStore(tmp_path / 'management', ROOT / 'agents')
    record = SandboxRecord('sbx_test', 'agent-code', 'alice', 'container-test', 4096, 'ready', 'image', '2026-09-10', '2026-09-10')
    registry = SimpleNamespace(list_sandboxes=lambda: [record], get_sandbox=lambda *args: record)
    runtime = SimpleNamespace(store=store, backend=SimpleNamespace(registry=registry),
                              lock=asyncio.Lock(), blocked=set(), drain=AsyncMock())
    runtime.records = AsyncMock(return_value=[])
    operations = Operations(runtime)
    runtime.operations = operations
    return operations


def test_search_and_pagination(service):
    assert service.list('ALICE')['total'] == 1
    assert service.list('container-test')['items'][0]['sandbox_id'] == 'sbx_test'
    assert service.list('missing')['items'] == []
    assert service.list(status='unhealthy')['total'] == 0
    assert service.list(offset=1)['items'] == []


def test_idempotent_operations_and_agent_scope_conflicts(service):
    jid, created = service.submit('sandbox.restart', 'sbx_test', 'request-1')
    assert created
    assert service.submit('sandbox.restart', 'sbx_test', 'request-1') == (jid, False)
    with pytest.raises(HTTPException):
        service.submit('sandbox.stop', 'sbx_test', 'request-1')
    with pytest.raises(HTTPException):
        service.submit('agent.archive', 'agent-code', 'request-2')


def test_archive_restore_preserves_configuration(service):
    before = copy.deepcopy(service.store.read()[1]['agents']['agent-code'])
    jid, _ = service.submit('agent.archive', 'agent-code', 'request-1')
    asyncio.run(service.run(jid))
    agent = service.store.read()[1]['agents']['agent-code']
    assert agent['lifecycle'] == 'archived'
    assert agent['versions'] == before['versions'] and agent['draft'] == before['draft']
    with pytest.raises(HTTPException):
        service.submit('sandbox.start', 'sbx_test', 'request-2')
    jid, _ = service.submit('agent.restore', 'agent-code', 'request-3')
    asyncio.run(service.run(jid))
    assert service.store.read()[1]['agents']['agent-code']['lifecycle'] == 'active'
    assert not service.runtime.blocked


def test_drain_failure_does_not_change_lifecycle(service):
    service.runtime.drain.side_effect = HTTPException(409, 'Busy')
    jid, _ = service.submit('agent.archive', 'agent-code', 'request-1')
    asyncio.run(service.run(jid))
    data = service.store.read()[1]
    assert data['jobs'][jid]['status'] == 'failed'
    assert data['agents']['agent-code'].get('lifecycle') is None
    assert not service.runtime.blocked


def test_empty_agent_delete_and_retired_id(service):
    cfg = copy.deepcopy(service.store.read()[1]['agents']['agent-code']['draft'])
    cfg['bindings'] = []
    service.store.save_agent('empty', cfg)
    jid, _ = service.submit('agent.delete-empty', 'empty', 'request-1')
    asyncio.run(service.run(jid))
    assert 'empty' not in service.store.read()[1]['agents']
    with pytest.raises(HTTPException):
        service.store.save_agent('empty', cfg)
    with pytest.raises(HTTPException):
        service.submit('agent.delete-empty', 'agent-code', 'request-2')


def test_manual_stop_blocks_request_acquisition(service):
    with service.store.edit() as data:
        data['sandbox_operations'] = {'sbx_test': {'desired_state': 'stopped'}}
    with pytest.raises(HTTPException, match='409'):
        service.check_acquire('agent-code', 'alice')


def test_operations_api_validates_limits_and_request_ids(service):
    app = FastAPI()
    app.include_router(create_operations_router(service.runtime))
    with TestClient(app) as client:
        assert client.get('/cloud/admin/sandboxes?q=alice').json()['total'] == 1
        assert client.get('/cloud/admin/sandboxes?limit=1000').status_code == 422
        assert client.post('/cloud/admin/sandboxes/sbx_test/restart', json={'request_id': ''}).status_code == 422


def test_restart_persists_stop_intent_and_does_not_repeat(service):
    backend = service.backend
    backend._locks = {}
    def stop(**kwargs):
        assert service.store.read()[1]['sandbox_operations']['sbx_test']['desired_state'] == 'stopped'
    container = SimpleNamespace(stop=Mock(side_effect=stop))
    backend._get_container = AsyncMock(return_value=container)
    backend._verify_ownership = Mock()
    backend._acquire_locked = AsyncMock()
    backend.registry.set_health_status = Mock()
    jid, _ = service.submit('sandbox.restart', 'sbx_test', 'request-1')
    asyncio.run(service.run(jid))
    data = service.store.read()[1]
    assert data['jobs'][jid]['status'] == 'succeeded'
    assert data['sandbox_operations']['sbx_test']['desired_state'] == 'running'
    assert backend._acquire_locked.await_count == 1
    asyncio.run(service.run(jid))
    assert container.stop.call_count == 1


def test_failed_start_keeps_manual_stop_intent(service):
    backend = service.backend
    backend._locks = {}
    backend._get_container = AsyncMock(return_value=None)
    backend._acquire_locked = AsyncMock(side_effect=RuntimeError('Docker unavailable'))
    jid, _ = service.submit('sandbox.start', 'sbx_test', 'request-1')
    asyncio.run(service.run(jid))
    data = service.store.read()[1]
    assert data['jobs'][jid]['status'] == 'failed'
    assert data['sandbox_operations']['sbx_test']['desired_state'] == 'stopped'


def test_pending_operation_prevents_agent_edits(service):
    cfg = service.store.read()[1]['agents']['agent-code']['draft']
    service.submit('agent.archive', 'agent-code', 'request-1')
    with pytest.raises(HTTPException):
        service.store.save_agent('agent-code', cfg)
