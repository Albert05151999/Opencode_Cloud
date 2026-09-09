import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from app.management import ManagementStore
from app.management_runtime import ManagementRuntime

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
def runtime(tmp_path):
    value = object.__new__(ManagementRuntime)
    value.store = ManagementStore(tmp_path / 'management', ROOT / 'agents')
    import asyncio
    value.lock = asyncio.Lock()
    value.blocked, value.requests, value.acquiring = set(), {}, {}
    value.backend = SimpleNamespace()
    return value


@pytest.mark.anyio
async def test_idle_uses_native_tasks_and_inflight_acquisition(runtime):
    runtime.records = AsyncMock(return_value=[SimpleNamespace(agent_id='agent-code', username='a')])
    runtime.backend.inspect = AsyncMock(return_value=SimpleNamespace(base_url='http://runtime', sandbox_id='sbx_test'))
    runtime.backend.registry = SimpleNamespace(list_sessions_for_sandbox=lambda _: [SimpleNamespace(session_id='ses_test')])
    runtime.client = SimpleNamespace(get=AsyncMock(return_value=httpx.Response(200, json={'s': {'type': 'busy'}}, request=httpx.Request('GET', 'http://runtime/session/status'))))
    assert not await runtime.idle({'agent-code'})
    runtime.client.get.return_value = httpx.Response(200, json={'s': {'type': 'idle'}}, request=httpx.Request('GET', 'http://runtime/session/status'))
    assert await runtime.idle({'agent-code'})
    runtime.acquiring['agent-code'] = 1
    assert not await runtime.idle({'agent-code'})


@pytest.mark.anyio
async def test_drain_timeout_preserves_candidate_without_removing_runtime(runtime, monkeypatch):
    runtime.idle = AsyncMock(return_value=False)
    times = iter([0, 121])
    monkeypatch.setattr('app.management_runtime.time', SimpleNamespace(monotonic=lambda: next(times)))
    with pytest.raises(HTTPException) as e:
        await runtime.drain({'agent-code'})
    assert e.value.status_code == 409


@pytest.mark.anyio
async def test_failed_validation_keeps_old_active_configuration(runtime):
    _, before = runtime.store.read()
    cfg = copy.deepcopy(before['agents']['agent-code']['draft'])
    jid = runtime.store.new_job('agent.apply', 'agent-code', {'config': cfg})
    runtime.compile_agent = lambda *args: Path('/fixture')
    runtime.probe = AsyncMock(side_effect=HTTPException(422, 'Invalid hook'))
    runtime.remove_sandboxes = AsyncMock()
    await runtime.apply_agent(jid)
    _, after = runtime.store.read()
    assert after['agents']['agent-code']['active'] == before['agents']['agent-code']['active']
    assert after['jobs'][jid]['status'] == 'failed'
    runtime.remove_sandboxes.assert_not_called()
    assert not runtime.blocked


@pytest.mark.anyio
async def test_agent_interrupted_job_recovery_keeps_old_version(runtime):
    jid = runtime.store.new_job('agent.apply', 'agent-code', {})
    runtime.store.job(jid, status='applying')
    await runtime.recover()
    _, data = runtime.store.read()
    assert data['agents']['agent-code']['active'] == 1
    assert data['jobs'][jid]['status'] == 'failed'


def test_all_model_bearing_shapes_are_validated(runtime):
    with pytest.raises(HTTPException) as e:
        runtime.authorize('agent-code', 'POST', 'session/test/summarize', {'providerID': 'cloud-model-gateway', 'modelID': 'data-fast'})
    assert e.value.status_code == 403
    payload = {'parts': []}
    runtime.authorize('agent-code', 'POST', 'session/test/prompt_async', payload)
    assert payload['model']['modelID'] == 'coding-fast'
    runtime.blocked.add('agent-code')
    with pytest.raises(HTTPException):
        runtime.authorize('agent-code', 'GET', 'event', {})
    assert not runtime.authorize('agent-code', 'POST', 'session/test/abort', {})


def test_disabled_agent_keeps_history_but_refuses_new_tasks(runtime):
    with runtime.store.edit() as data:
        data['agents']['agent-code']['versions'][0]['config']['enabled'] = False
    assert not runtime.authorize('agent-code', 'GET', 'session/test/message', {})
    with pytest.raises(HTTPException) as e:
        runtime.authorize('agent-code', 'POST', 'session/test/prompt_async', {})
    assert e.value.status_code == 409
