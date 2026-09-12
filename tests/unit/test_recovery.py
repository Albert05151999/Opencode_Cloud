import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, Mock

from app.recovery import RecoveryPolicy
from test_operations import service


def prepare(service):
    record = replace(service.find('sbx_test'), status='unhealthy')
    service.backend.registry.list_sandboxes = lambda: [record]
    service.backend.client = Mock(ping=Mock(return_value=True))
    service.runtime.requests = {}
    service.runtime.acquiring = {}
    service.runtime.spawn = Mock(side_effect=lambda coro: coro.close())
    service.recovery.save_policy(RecoveryPolicy(failure_threshold=1, max_attempts=1))
    service.recovery.idle_evidence = AsyncMock(return_value=True)
    return record


def test_recovery_attempts_are_bounded_and_persistent(service):
    prepare(service)
    service.submit = Mock(return_value=('job_recover', True))
    asyncio.run(service.recovery.tick())
    assert service.submit.call_count == 1
    service.recovery.update('sbx_test', next_attempt=0)
    asyncio.run(service.recovery.tick())
    assert service.submit.call_count == 1
    assert 'limit' in service.recovery.state('sbx_test')['reason']


def test_manual_stop_and_global_failure_never_recover(service):
    prepare(service)
    service.submit = Mock()
    with service.store.edit() as data:
        data['sandbox_operations'] = {'sbx_test': {'desired_state': 'stopped'}}
    asyncio.run(service.recovery.tick())
    asyncio.run(service.recovery.tick(False))
    assert not service.submit.called


def test_busy_or_unknown_execution_is_not_restarted(service):
    prepare(service)
    service.submit = Mock()
    service.recovery.idle_evidence = AsyncMock(return_value=False)
    asyncio.run(service.recovery.tick())
    assert not service.submit.called
    assert 'unknown' in service.recovery.state('sbx_test')['reason']


def test_idle_evidence_invalidated_before_new_execution(service):
    record = service.find('sbx_test')
    service.runtime.requests = {}
    service.runtime.acquiring = {}
    service.backend.inspect = AsyncMock(return_value=None)
    assert not asyncio.run(service.recovery.idle_evidence(record))
    service.recovery.update(record.sandbox_id, execution='idle', container_id=record.container_id)
    assert asyncio.run(service.recovery.idle_evidence(record))
    service.recovery.invalidate_idle(record.agent_id)
    assert not asyncio.run(service.recovery.idle_evidence(record))


def test_stale_idle_probe_cannot_overwrite_new_activity(service, monkeypatch):
    record = service.find('sbx_test')
    service.runtime.requests = {}
    service.runtime.acquiring = {}
    service.runtime.client = Mock()
    service.backend.inspect = AsyncMock(return_value=Mock())
    async def probe(*args, **kwargs):
        service.recovery.invalidate_idle(record.agent_id)
        return {}
    monkeypatch.setattr('app.recovery.directory_collection', probe)
    assert not asyncio.run(service.recovery.idle_evidence(record))
    assert service.recovery.state(record.sandbox_id)['execution'] == 'unknown'
