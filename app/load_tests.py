"""Server-initiated load execution; uses the public session API and owned users."""
import asyncio
import shutil
import time
from pathlib import Path

import httpx

from app.load_test_store import ACTIVE, PREFIX, PROMPT, LoadRequest, LoadTestStore
from app.management import fail
from app.sandbox import sandbox_key
from app.load_capacity import LoadCapacity, check_capacity


class LoadTests:
    def __init__(self, runtime):
        self.runtime, self.backend = runtime, runtime.backend
        self.store = LoadTestStore(runtime.store)
        self.tasks = {}
        self.api_factory = None
        self.capacity = LoadCapacity(self.backend)
        self.admission_lock = asyncio.Lock()

    def bind(self, application, token):
        self.api_factory = lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=application),
            base_url='http://loadtest.internal', headers={'Authorization': 'Bearer ' + token}, timeout=None)

    def resources_for(self, aid, username):
        if not username.startswith(PREFIX):
            return None
        user = self.store.user(aid, username)
        if not user or user['storage_state'] != 'retained':
            fail('Load-test user is unavailable or being cleaned up', 409)
        return user

    def owns_user(self, username):
        return username.startswith(PREFIX)

    def active_user(self, aid, username):
        return self.store.active_user(aid, username)

    async def options(self):
        _, data = self.runtime.store.read()
        agents = []
        for aid, agent in data['agents'].items():
            config = self.runtime.store.agent_config(agent)
            if config and config.get('enabled', True) and agent.get('lifecycle', 'active') == 'active':
                agents.append({'id': aid, 'name': config['name'], 'version': agent['active'], 'model_id': config['default_model_id']})
        capacity = await self.capacity.snapshot()
        return {'agents': agents, 'max_users': 100, 'prepare_concurrency': 4, 'prompt': PROMPT,
                'defaults': {'users': 1, 'cpu_limit': 1, 'memory_mb': 1024, 'timeout_seconds': 180},
                'host_capacity': capacity}

    async def admit_start(self, request):
        async with self.admission_lock:
            previous = self.store.previous(request)
            if previous:
                return {'id': previous, 'created': False}
            self.store.validate_agents(request)
            snapshot = await self.capacity.snapshot(fresh=True)
            check_capacity(snapshot, [a.model_dump() for a in request.agents])
            result = self.start(request)
            self.store.update(result['id'], admission_capacity=snapshot)
            return result

    async def capacity_check(self, rid, users):
        snapshot = await self.capacity.snapshot(fresh=True)
        report = self.store.get(rid)
        samples = report.get('capacity_checks', []) + [snapshot]
        self.store.update(rid, capacity_checks=samples[-30:])
        try:
            check_capacity(snapshot, users)
        except Exception:
            self.store.update(rid, capacity_blocked=True)
            for user in users:
                if user.get('username'):
                    self.store.update_user(user['username'], phase='prepare_failed', error='CAPACITY_BLOCKED', finished_at=time.time())
            raise

    def _spawn(self, key, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks[key] = task
        self.runtime.tasks.add(task)
        task.add_done_callback(self.runtime.tasks.discard)
        def done(finished):
            if self.tasks.get(key) is finished:
                self.tasks.pop(key, None)
        task.add_done_callback(done)

    def start(self, request):
        if self.api_factory is None:
            fail('Load-test API is not initialized', 503)
        rid, created = self.store.create(request)
        if created:
            self._spawn(rid, self.run(rid))
        return {'id': rid, 'created': created}

    async def _abort(self, api, session_id):
        if not session_id:
            return False
        try:
            response = await asyncio.wait_for(api.post('/session/' + session_id + '/abort', json={}), 10)
            return response.is_success
        except Exception:
            return False  # Explicit cleanup can terminate an unreachable test container.

    def _record_session(self, user, response):
        response.raise_for_status()
        session = response.json()
        sid = session.get('id')
        if not isinstance(sid, str) or not sid.startswith('ses_'):
            raise ValueError('Invalid session response')
        self.store.update_user(user['username'], session_id=sid,
            sandbox_id='sbx_' + sandbox_key(user['agent_id'], user['username']))
        return sid

    async def _prepare(self, api, user, limit, timeout):
        async with limit:
            started = time.time()
            self.store.update_user(user['username'], phase='preparing', prepare_started_at=started)
            request = asyncio.create_task(api.post('/session', json={'title': 'Load test',
                '_cloud': {'agent_id': user['agent_id'], 'username': user['username']}}))
            try:
                response = await asyncio.wait_for(asyncio.shield(request), timeout)
                self._record_session(user, response)
                self.store.update_user(user['username'], phase='ready', prepare_ms=round((time.time() - started) * 1000, 2))
            except (asyncio.CancelledError, TimeoutError) as exc:
                # Docker creation runs in a thread. Let that request settle before
                # allowing cleanup, otherwise a container could appear after deletion.
                try:
                    self._record_session(user, await asyncio.shield(request))
                except Exception:
                    pass
                self.store.update_user(user['username'], phase='cancelled' if isinstance(exc, asyncio.CancelledError) else 'prepare_failed',
                    error='CANCELLED' if isinstance(exc, asyncio.CancelledError) else 'PREPARE_TIMEOUT',
                    prepare_ms=round((time.time() - started) * 1000, 2), finished_at=time.time())
                if isinstance(exc, asyncio.CancelledError):
                    raise
            except Exception as exc:
                self.store.update_user(user['username'], phase='prepare_failed', error=self.error_code(exc),
                                       prepare_ms=round((time.time() - started) * 1000, 2), finished_at=time.time())

    @staticmethod
    def error_code(exc):
        return 'HTTP_' + str(exc.response.status_code) if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__

    async def _generate(self, api, user, barrier, timeout, model):
        await barrier.wait()
        started = time.time()
        self.store.update_user(user['username'], phase='running', sent_at=started)
        try:
            response = await asyncio.wait_for(api.post('/session/' + user['session_id'] + '/message', json={
                'model': {'providerID': 'cloud-model-gateway', 'modelID': model},
                'parts': [{'type': 'text', 'text': PROMPT}]}), timeout)
            response.raise_for_status()
            body = response.json()
            info = body.get('info', {})
            text = ''.join(p.get('text', '') for p in body.get('parts', []) if p.get('type') == 'text')
            error = 'MODEL_ERROR' if info.get('error') or body.get('error') else None
            if not error and not text.strip():
                error = 'EMPTY_RESPONSE'
            tokens = info.get('tokens') or {}
            self.store.update_user(user['username'], phase='failed' if error else 'succeeded', error=error,
                response_matches='LOAD-TEST-OK' in text, input_tokens=tokens.get('input', 0) or 0,
                output_tokens=tokens.get('output', 0) or 0)
        except (asyncio.CancelledError, TimeoutError) as exc:
            aborted = await self._abort(api, user['session_id'])
            self.store.update_user(user['username'], phase='cancelled' if isinstance(exc, asyncio.CancelledError) else 'timed_out',
                                   abort_confirmed=aborted,
                                   error='CANCELLED' if isinstance(exc, asyncio.CancelledError) else 'REQUEST_TIMEOUT')
            if isinstance(exc, asyncio.CancelledError):
                raise
        except Exception as exc:
            aborted = await self._abort(api, user['session_id'])
            self.store.update_user(user['username'], phase='failed', error=self.error_code(exc), abort_confirmed=aborted)
        finally:
            self.store.update_user(user['username'], latency_ms=round((time.time() - started) * 1000, 2), finished_at=time.time())

    async def run(self, rid):
        children = []
        try:
            # Pin active versions and model gateway while the experiment runs.
            # Chat is not locked; configuration and lifecycle operations queue.
            async with self.runtime.lock:
                report = self.store.get(rid)
                if report['status'] not in ACTIVE:
                    return
                request = LoadRequest.model_validate(report['request'])
                snapshots = self.store.validate_agents(request)
                if snapshots != report['snapshots']:
                    fail('Agent configuration changed before test start; create a new test', 409)
                self.store.update(rid, status='preparing', started_at=time.time())
                async with self.api_factory() as api:
                    limit = asyncio.Semaphore(4)
                    # Wait for a complete batch before re-sampling so pending
                    # creations cannot be omitted from the next budget.
                    for offset in range(0, len(report['users']), 4):
                        await self.capacity_check(rid, report['users'][offset:])
                        children = [asyncio.create_task(self._prepare(api, u, limit, request.prepare_timeout_seconds)) for u in report['users'][offset:offset + 4]]
                        await self._join(children)
                    await self.capacity_check(rid, [])
                    ready = [u for u in self.store.get(rid)['users'] if u['phase'] == 'ready']
                    if not ready:
                        self.store.update(rid, status='failed', error='No sessions were prepared')
                        return
                    self.store.update(rid, status='running', generation_started_at=time.time())
                    barrier = asyncio.Event()
                    children = [asyncio.create_task(self._generate(api, u, barrier, request.timeout_seconds,
                        snapshots[u['agent_id']]['model_id'])) for u in ready]
                    barrier.set()
                    await self._join(children)
                    users = self.store.get(rid)['users']
                    self.store.update(rid, status='completed' if all(u['phase'] == 'succeeded' for u in users) else 'completed_with_errors')
        except asyncio.CancelledError:
            # gather cancels children, which settle creation / abort generation.
            for child in children:
                if not child.done() and not child.cancelling():
                    child.cancel()
            await asyncio.gather(*children, return_exceptions=True)
            cancelled = self.store.get(rid).get('cancel_requested', False)
            self.store.update(rid, status='cancelled' if cancelled else 'interrupted')
        except Exception as exc:
            from fastapi import HTTPException
            self.store.update(rid, status='failed', error=str(exc.detail) if isinstance(exc, HTTPException) else self.error_code(exc))
        finally:
            report = self.store.get(rid)
            for user in report['users']:
                if user['phase'] in {'queued', 'preparing', 'ready', 'running'}:
                    self.store.update_user(user['username'], phase='cancelled' if report.get('cancel_requested') or report.get('capacity_blocked') else 'interrupted', finished_at=time.time())
            self.store.update(rid, finished_at=time.time())

    @staticmethod
    async def _join(children):
        try:
            await asyncio.gather(*children)
        except BaseException:
            for child in children:
                if not child.done() and not child.cancelling():
                    child.cancel()
            await asyncio.gather(*children, return_exceptions=True)
            raise

    def cancel(self, rid):
        report = self.store.get(rid)
        if report['status'] not in ACTIVE or report.get('cancel_requested'):
            return {'id': rid, 'status': report['status']}
        self.store.update(rid, status='cancelling', cancel_requested=True)
        task = self.tasks.get(rid)
        if task and not task.done():
            # Schedule cancellation after run() has entered its try/finally.
            asyncio.get_running_loop().call_soon(task.cancel)
        else:
            self.store.update(rid, status='cancelled', finished_at=time.time())
        return {'id': rid, 'status': 'cancelling'}

    def cleanup(self, rid, confirmation):
        if confirmation != rid:
            fail('Type the exact test ID to confirm destruction')
        report = self.store.get(rid)
        if report['status'] in ACTIVE or rid in self.tasks:
            fail('Wait for the test to stop before cleanup', 409)
        if report['cleanup_status'] in {'cleaning', 'cleaned'}:
            return {'id': rid, 'cleanup_status': report['cleanup_status']}
        self.store.update(rid, cleanup_status='cleaning', cleanup_error=None)
        for user in report['users']:
            if user['storage_state'] != 'cleaned':
                self.store.update_user(user['username'], storage_state='cleaning')
        self._spawn('cleanup:' + rid, self._cleanup(rid))
        return {'id': rid, 'cleanup_status': 'cleaning'}

    def _user_roots(self, user):
        roots = []
        for base in (self.backend.workspaces.workspace_root, self.backend.workspaces.state_root):
            base = Path(base).resolve(strict=True)
            target = base / user['agent_id'] / user['username']
            if target.is_symlink() or target.resolve() != target or target.parent.parent != base:
                fail('Test user storage path changed; inspect before cleanup', 409)
            roots.append(target)
        return roots

    async def _cleanup(self, rid):
        try:
            async with self.runtime.lock:
                for user in self.store.get(rid)['users']:
                    aid, name = user['agent_id'], user['username']
                    if user['storage_state'] == 'cleaned':
                        continue
                    lock = self.backend._locks.setdefault((aid, name), asyncio.Lock())
                    async with lock:
                        roots = self._user_roots(user)
                        key = sandbox_key(aid, name)
                        if self.backend.in_use.get('sbx_' + key, 0):
                            fail('A request still uses this test sandbox; retry cleanup', 409)
                        record = self.backend.registry.get_sandbox(aid, name)
                        container = await self.backend._find_existing(record, key, aid, name)
                        if container:
                            labels = container.attrs.get('Config', {}).get('Labels') or {}
                            if labels.get('cloud.load_test') != rid:
                                fail('Container is not owned by this load test', 409)
                            await self.backend._remove_owned(container)
                        for root in roots:
                            if root.exists():
                                await asyncio.to_thread(shutil.rmtree, root)
                        with self.backend.registry.connect() as db:
                            db.execute('DELETE FROM sessions WHERE agent_id=? AND username=?', (aid, name))
                            db.execute('DELETE FROM sandboxes WHERE agent_id=? AND username=?', (aid, name))
                        self.store.update_user(name, storage_state='cleaned', cleaned_at=time.time())
                self.store.update(rid, cleanup_status='cleaned', cleaned_at=time.time())
        except asyncio.CancelledError:
            self.store.update(rid, cleanup_status='failed', cleanup_error='Cleanup interrupted; retry')
        except Exception as exc:
            self.store.update(rid, cleanup_status='failed', cleanup_error=self.error_code(exc))
