import asyncio
import copy
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.load_test_api import create_load_test_router
from app.load_test_store import LoadRequest, LoadTestStore, PROMPT, report_csv, summarize
from app.load_tests import LoadTests
from app.management import ManagementStore
from app.registry import Registry
from app.workspace import WorkspaceManager
from test_sandbox import backend_factory

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def service(tmp_path):
    store = ManagementStore(tmp_path / 'management', ROOT / 'agents')
    registry = Registry(tmp_path / 'registry.db')
    registry.initialize()
    backend = SimpleNamespace(registry=registry, workspaces=WorkspaceManager(tmp_path / 'workspaces', tmp_path / 'state'),
        _locks={}, in_use={}, _find_existing=AsyncMock(return_value=None), _remove_owned=AsyncMock(),
        client=SimpleNamespace(info=Mock(return_value={'NCPU': 8, 'MemTotal': 16 * 1024**3})))
    runtime = SimpleNamespace(store=store, backend=backend, lock=asyncio.Lock(), tasks=set())
    value = LoadTests(runtime)
    value.capacity.snapshot = AsyncMock(side_effect=lambda **kw: {
        'known': True, 'admission_allowed': True, 'sampled_at': time.time(), 'reasons': [],
        'remaining_cpu': 8, 'remaining_memory_mb': 16384, 'cpu_count': 8, 'memory_mb': 16384})
    backend.workspaces.user_guard = value.resources_for
    return value


def payload(**kwargs):
    return LoadRequest.model_validate(dict(request_id='unique-test-1', agents=[{'agent_id': 'agent-code', 'users': 2}], **kwargs))


def test_parameters_existing_agents_and_no_catalog_changes(service):
    before = service.runtime.store.read()
    rid, created = service.store.create(payload())
    assert created and service.store.create(payload()) == (rid, False)
    assert service.runtime.store.read() == before
    with pytest.raises(HTTPException):
        service.store.create(payload(timeout_seconds=30))
    with pytest.raises(HTTPException):
        service.store.create(LoadRequest(request_id='another-run', agents=[{'agent_id': 'unknown'}]))
    for agents in ([{'agent_id': 'agent-code', 'users': 101}], [{'agent_id': 'agent-code', 'cpu_limit': 0}],
                   [{'agent_id': 'agent-code', 'memory_mb': 128}], [{'agent_id': 'agent-code'}] * 2):
        with pytest.raises(ValidationError):
            LoadRequest(request_id='validation', agents=agents)


def test_lifecycle_operation_cannot_block_test_requests_while_preparing(service):
    from app.operations import Operations
    service.runtime.load_tests = service
    operations = Operations(service.runtime)
    service.store.create(payload())
    before = service.runtime.store.read()
    with pytest.raises(HTTPException) as error:
        operations.submit('agent.archive', 'agent-code', 'archive-during-test')
    assert error.value.status_code == 409
    assert service.runtime.store.read() == before


def test_unpublished_and_archived_agents_cannot_run(service):
    cfg = copy.deepcopy(service.runtime.store.read()[1]['agents']['agent-code']['draft'])
    cfg['bindings'] = []
    service.runtime.store.save_agent('unpublished', cfg)
    with pytest.raises(HTTPException):
        service.store.create(LoadRequest(request_id='unpublished-1', agents=[{'agent_id': 'unpublished'}]))
    with service.runtime.store.edit() as data:
        data['agents']['agent-code']['lifecycle'] = 'archived'
    with pytest.raises(HTTPException):
        service.store.create(payload())


def test_users_are_unique_and_resources_survive_reload(service):
    rid, _ = service.store.create(payload())
    users = service.store.get(rid)['users']
    restored = LoadTestStore(service.runtime.store)
    assert len({u['username'] for u in users}) == 2
    assert restored.user('agent-code', users[0]['username'])['cpu_limit'] == 1
    assert service.resources_for('agent-code', 'normal-user') is None
    assert restored.user('agent-data', users[0]['username']) is None
    with pytest.raises(HTTPException):
        service.resources_for('agent-data', users[0]['username'])


def test_docker_receives_test_limits_without_changing_agent_defaults(service, backend_factory):
    backend, registry, docker, agents = backend_factory()
    backend.management = SimpleNamespace(load_tests=service)
    rid, _ = service.store.create(LoadRequest(request_id='resources-test', agents=[
        {'agent_id': 'agent-code', 'cpu_limit': .5, 'memory_mb': 1536}]))
    user = service.store.get(rid)['users'][0]
    async def create(name):
        layout = backend.workspaces.ensure_user_layout('agent-code', name)
        return await backend._create_container(name, 'agent-code', name, agents / 'agent-code', layout.workspace, layout.state)
    asyncio.run(create(user['username']))
    asyncio.run(create('normal-user'))
    test, normal = docker.containers.create_calls
    assert test['nano_cpus'] == 500_000_000 and test['mem_limit'] == '1536m'
    assert test['labels']['cloud.load_test'] == rid
    assert normal['nano_cpus'] == 1_500_000_000 and normal['mem_limit'] == '768m'
    assert 'cloud.load_test' not in normal['labels']


def test_all_sessions_prepared_before_single_concurrent_submission(service):
    async def run():
        prepared, received = [], []
        both = asyncio.Event()
        async def handler(request):
            body = json.loads(request.content)
            if request.url.path == '/session':
                prepared.append(body['_cloud']['username'])
                return httpx.Response(200, json={'id': 'ses_' + str(len(prepared))})
            assert len(prepared) == 2
            assert body['parts'] == [{'type': 'text', 'text': PROMPT}]
            received.append(request.url.path)
            if len(received) == 2:
                both.set()
            await asyncio.wait_for(both.wait(), 2)
            return httpx.Response(200, json={'info': {'tokens': {'input': 4, 'output': 2}}, 'parts': [{'type': 'text', 'text': 'LOAD-TEST-OK'}]})
        service.api_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')
        rid = service.start(payload())['id']
        assert not service.start(payload())['created']
        await service.tasks[rid]
        report = service.store.get(rid)
        assert report['status'] == 'completed' and len(set(received)) == 2
        assert report['summary']['succeeded'] == 2 and report['summary']['input_tokens'] == 8
        assert report['by_agent']['agent-code']['submitted'] == 2
    asyncio.run(run())


def test_model_error_with_http_200_is_failure(service):
    async def run():
        async def handler(request):
            if request.url.path == '/session':
                return httpx.Response(200, json={'id': 'ses_' + json.loads(request.content)['_cloud']['username']})
            return httpx.Response(200, json={'info': {'error': {'name': 'APIError'}}, 'parts': []})
        service.api_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')
        rid = service.start(payload())['id']
        await service.tasks[rid]
        report = service.store.get(rid)
        assert report['status'] == 'completed_with_errors' and report['summary']['failed'] == 2
    asyncio.run(run())


def test_cancel_aborts_requests_without_replay_or_deletion(service):
    async def run():
        generating, aborted = asyncio.Event(), []
        async def handler(request):
            if request.url.path == '/session':
                return httpx.Response(200, json={'id': 'ses_' + json.loads(request.content)['_cloud']['username']})
            if request.url.path.endswith('/abort'):
                aborted.append(request.url.path)
                return httpx.Response(200, json=True)
            generating.set()
            await asyncio.Event().wait()
        service.api_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')
        rid = service.start(payload())['id']
        task = service.tasks[rid]
        await asyncio.wait_for(generating.wait(), 2)
        service.cancel(rid)
        await task
        report = service.store.get(rid)
        assert report['status'] == 'cancelled' and len(aborted) == 2
        assert report['cleanup_status'] == 'retained'
        service.store.recover()
        assert service.store.get(rid)['status'] == 'cancelled'
    asyncio.run(run())


def test_cancel_during_preparation_waits_for_creation_to_settle(service):
    async def run():
        started, finish = asyncio.Event(), asyncio.Event()
        async def handler(request):
            assert request.url.path == '/session'
            started.set()
            await finish.wait()
            return httpx.Response(200, json={'id': 'ses_' + json.loads(request.content)['_cloud']['username']})
        service.api_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')
        rid = service.start(payload())['id']
        task = service.tasks[rid]
        await started.wait()
        service.cancel(rid)
        await asyncio.sleep(.01)
        with pytest.raises(HTTPException):
            service.cleanup(rid, rid)
        assert not task.done()
        finish.set()
        await task
        assert service.store.get(rid)['summary']['prepared'] == 2
        assert service.store.get(rid)['summary']['submitted'] == 0
    asyncio.run(run())


def test_request_timeout_aborts_and_reports_failure(service):
    async def run():
        rid, _ = service.store.create(payload())
        user = service.store.get(rid)['users'][0]
        user['session_id'] = 'ses_timeout'
        aborted = []
        async def handler(request):
            if request.url.path.endswith('/abort'):
                aborted.append(request.url.path)
                return httpx.Response(200, json=True)
            await asyncio.Event().wait()
        barrier = asyncio.Event()
        barrier.set()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test') as api:
            await service._generate(api, user, barrier, .01, 'coding-fast')
        result = service.store.user('agent-code', user['username'])
        assert result['phase'] == 'timed_out' and result['abort_confirmed']
        assert aborted == ['/session/ses_timeout/abort']
    asyncio.run(run())


def test_one_prepare_failure_does_not_hide_or_repeat_other_users(service):
    async def run():
        prepared, submitted = [], []
        async def handler(request):
            if request.url.path == '/session':
                prepared.append(1)
                return httpx.Response(503 if len(prepared) == 1 else 200, json={'id': 'ses_ready'})
            submitted.append(1)
            return httpx.Response(200, json={'parts': [{'type': 'text', 'text': 'LOAD-TEST-OK'}]})
        service.api_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')
        rid = service.start(payload())['id']
        await service.tasks[rid]
        report = service.store.get(rid)
        assert report['status'] == 'completed_with_errors'
        assert report['summary']['submitted'] == len(submitted) == 1
        assert report['summary']['success_rate'] == .5
    asyncio.run(run())


def test_immediate_cancel_leaves_no_permanently_active_run(service):
    async def run():
        async def handler(request):
            return httpx.Response(200, json={'id': 'ses_ready'})
        service.api_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url='http://test')
        rid = service.start(payload())['id']
        task = service.tasks[rid]
        service.cancel(rid)
        await task
        assert service.store.get(rid)['status'] == 'cancelled'
        assert service.store.list()['active_id'] is None
    asyncio.run(run())


def test_restart_marks_active_run_interrupted_without_replay(service):
    rid, _ = service.store.create(payload())
    user = service.store.get(rid)['users'][0]
    service.store.update_user(user['username'], phase='running', sent_at=1)
    service.store.update(rid, status='running')
    LoadTestStore(service.runtime.store).recover()
    report = service.store.get(rid)
    assert report['status'] == 'interrupted' and report['summary']['failed'] == 2
    assert not service.tasks


def test_cleanup_only_owned_users_and_preserves_report(service):
    async def run():
        rid, _ = service.store.create(payload())
        users = service.store.get(rid)['users']
        workspace = service.backend.workspaces
        normal = workspace.ensure_user_layout('agent-code', 'normal-user').workspace / 'normal.txt'
        normal.write_text('keep')
        for user in users:
            workspace.ensure_user_layout('agent-code', user['username']).workspace.joinpath('test.txt').write_text('test')
        with pytest.raises(HTTPException):
            service.cleanup(rid, rid)
        service.store.update(rid, status='completed')
        with pytest.raises(HTTPException):
            service.cleanup(rid, 'wrong-id')
        service.cleanup(rid, rid)
        assert service.cleanup(rid, rid)['cleanup_status'] == 'cleaning'
        await service.tasks['cleanup:' + rid]
        report = service.store.get(rid)
        assert report['cleanup_status'] == 'cleaned' and len(report['users']) == 2
        assert normal.read_text() == 'keep'
        for user in users:
            assert not (workspace.workspace_root / 'agent-code' / user['username']).exists()
            with pytest.raises(HTTPException):
                workspace.ensure_user_layout('agent-code', user['username'])
        assert service.cleanup(rid, rid)['cleanup_status'] == 'cleaned'
    asyncio.run(run())


def test_cleanup_rejects_container_without_test_ownership_and_retries(service):
    async def run():
        rid, _ = service.store.create(payload())
        service.store.update(rid, status='completed')
        container = SimpleNamespace(attrs={'Config': {'Labels': {}}})
        service.backend._find_existing.return_value = container
        service.cleanup(rid, rid)
        await service.tasks['cleanup:' + rid]
        assert service.store.get(rid)['cleanup_status'] == 'failed'
        service.backend._remove_owned.assert_not_awaited()
        container.attrs['Config']['Labels']['cloud.load_test'] = rid
        service.cleanup(rid, rid)
        await service.tasks['cleanup:' + rid]
        assert service.store.get(rid)['cleanup_status'] == 'cleaned'
    asyncio.run(run())


def test_report_math_and_csv(service):
    users = [{'phase': 'succeeded', 'latency_ms': n, 'sent_at': 10, 'finished_at': 11} for n in [100, 200, 300]]
    summary = summarize(users)
    assert summary['p50_ms'] == 200 and summary['p95_ms'] == 300 and summary['successful_requests_per_second'] == 3
    assert summarize([])['p95_ms'] is None
    rid, _ = service.store.create(payload())
    csv = report_csv(service.store.get(rid))
    assert csv.startswith('\ufeffagent_id,username') and csv.count('loadtest-') == 2


def test_report_routes_validate_payload_and_offer_downloads(service):
    rid, _ = service.store.create(payload())
    app = FastAPI()
    app.include_router(create_load_test_router(service))
    with TestClient(app) as client:
        assert client.get('/cloud/admin/load-tests/options').json()['host_capacity']['cpu_count'] == 8
        assert client.get('/cloud/admin/load-tests?limit=1000').status_code == 422
        assert client.post('/cloud/admin/load-tests', json={'agents': []}).status_code == 422
        assert client.get(f'/cloud/admin/load-tests/{rid}/report?format=csv').headers['content-type'].startswith('text/csv')
        assert client.get('/cloud/admin/load-tests/missing').status_code == 404
