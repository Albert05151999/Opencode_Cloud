import asyncio
from dataclasses import replace
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.config import LoadCapacityConfig, load_config, ConfigurationError
from app.load_capacity import LoadCapacity, calculate, check_capacity
from app.load_test_store import LoadRequest
from test_load_tests import service, payload, ROOT


def snapshot(containers=(), available=12000, usage=20, policy=LoadCapacityConfig()):
    return calculate({'NCPU': 8, 'MemTotal': 16000 * 1024**2},
        {'memory_mb': 16000, 'memory_available_mb': available, 'cpu_usage_percent': usage}, containers, policy)


def container(cpu=2, memory=4000, usage=1000, status='running', sandbox=True):
    return {'id': 'c1', 'labels': {'cloud.agent_id': 'agent-code'} if sandbox else {},
            'status': status, 'host_config': {'NanoCpus': cpu * 1e9, 'Memory': memory * 1024**2},
            'memory_usage_mb': usage}


def test_budget_deducts_current_usage_future_growth_and_system_reserve():
    result = snapshot([container()], available=7000)
    assert result['reserved_memory_mb'] == 1600
    assert result['remaining_memory_mb'] == 2400  # 7000 - 3000 unconsumed quota - 1600 reserve
    assert result['remaining_cpu'] == 5
    assert result['cpu_usage_percent'] == 20
    assert result['running_sandboxes'] == 1


def test_stopped_sandbox_keeps_its_restartable_allocation():
    result = snapshot([container(status='exited')])
    assert result['allocated_memory_mb'] == 4000
    assert result['remaining_memory_mb'] == 6400
    assert result['running_sandboxes'] == 0


def test_unlimited_sandbox_busy_cpu_unknown_host_or_stale_data_blocks():
    for result in (snapshot([container(cpu=0)]), snapshot(usage=95), snapshot(available=500),
                   {'known': False}, dict(snapshot(), sampled_at=time.time() - 30)):
        with pytest.raises(HTTPException):
            check_capacity(result, [])
    with pytest.raises(ValueError):
        calculate({'NCPU': 8, 'MemTotal': 2000 * 1024**2},
                  {'memory_mb': 16000, 'memory_available_mb': 14000, 'cpu_usage_percent': 10}, [], LoadCapacityConfig())


def test_overcommit_returns_actionable_maximum_without_mutating_request():
    rows = [{'agent_id': 'agent-code', 'users': 8, 'cpu_limit': 1, 'memory_mb': 1024}]
    with pytest.raises(HTTPException) as error:
        check_capacity(snapshot(), rows)
    assert error.value.status_code == 409
    assert '最多 7 用户' in error.value.detail
    assert rows[0]['users'] == 8
    check_capacity(snapshot(), [dict(rows[0], users=7)])


def test_sampler_failure_does_not_reuse_green_cache():
    async def run():
        value = LoadCapacity(SimpleNamespace())
        value._cached = snapshot()
        value._sample = lambda: (_ for _ in ()).throw(RuntimeError('Docker unavailable'))
        assert not (await value.snapshot(fresh=True))['known']
        assert value._cached is None
        assert not (await value.snapshot())['known']
    asyncio.run(run())


def test_rejected_admission_creates_no_test_users_and_retry_is_idempotent(service):
    async def run():
        service.api_factory = lambda: None
        service.capacity.snapshot = AsyncMock(return_value=dict(snapshot(), remaining_cpu=0))
        with pytest.raises(HTTPException):
            await service.admit_start(payload())
        assert service.store.list()['total'] == 0
        with service.runtime.store.connect() as db:
            assert db.execute('SELECT count(*) FROM load_test_users').fetchone()[0] == 0
        # A duplicate accepted request is still discoverable when the host is full.
        rid, _ = service.store.create(payload())
        assert await service.admit_start(payload()) == {'id': rid, 'created': False}
    asyncio.run(run())


def test_capacity_drop_after_first_batch_prevents_remaining_containers_and_generation(service):
    import httpx, json
    async def run():
        calls = []
        async def handler(request):
            calls.append(request.url.path)
            assert request.url.path == '/session'
            return httpx.Response(200, json={'id': 'ses_' + json.loads(request.content)['_cloud']['username']})
        service.api_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')
        service.capacity.snapshot = AsyncMock(side_effect=[snapshot(), dict(snapshot(), remaining_cpu=0)])
        rid = service.start(LoadRequest(request_id='capacity-drop', agents=[{'agent_id': 'agent-code', 'users': 5}]))['id']
        await service.tasks[rid]
        result = service.store.get(rid)
        assert result['status'] == 'failed' and result['capacity_blocked']
        assert len(calls) == 4 and result['summary']['submitted'] == 0
        assert len(result['capacity_checks']) == 2
        assert result['cleanup_status'] == 'retained'
    asyncio.run(run())


def test_reserve_configuration_is_optional_and_validated(tmp_path):
    import configparser
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(ROOT / 'config.cfg')
    cfg.remove_section('load_capacity')
    target = tmp_path / 'config.cfg'
    with target.open('w') as stream:
        cfg.write(stream)
    assert load_config(target, environ={}).load_capacity == LoadCapacityConfig()
    cfg['load_capacity'] = {'reserved_cpu': '2', 'reserved_memory_mb': '2048', 'reserve_fraction': '.2', 'max_cpu_usage_percent': '85'}
    with target.open('w') as stream:
        cfg.write(stream)
    assert load_config(target, environ={}).load_capacity.reserved_cpu == 2
    cfg['load_capacity']['reserve_fraction'] = 'nan'
    with target.open('w') as stream:
        cfg.write(stream)
    with pytest.raises(ConfigurationError):
        load_config(target, environ={})
