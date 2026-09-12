"""Platform operations, independent of HTTP and presentation concerns."""
import asyncio
import time
import uuid
from dataclasses import asdict

from fastapi import HTTPException

from app.management import fail

ACTIVE = {'queued', 'validating', 'waiting', 'applying'}


class Operations:
    def __init__(self, runtime):
        self.runtime = runtime
        self.store = runtime.store
        self.backend = runtime.backend
        from app.recovery import Recovery
        self.recovery = Recovery(self)
        from app.agent_deletion import AgentDeletion
        self.deletion = AgentDeletion(self)
        from app.sandbox_details import SandboxDetails
        self.details = SandboxDetails(self)

    def find(self, sid):
        record = next((r for r in self.backend.registry.list_sandboxes() if r.sandbox_id == sid), None)
        if record is None:
            fail('Sandbox not found', 404)
        return record

    def list(self, query='', status=None, offset=0, limit=50):
        _, data = self.store.read()
        rows = []
        for record in self.backend.registry.list_sandboxes():
            row = asdict(record)
            state = data.get('sandbox_operations', {}).get(record.sandbox_id, {})
            row['recovery'] = self.recovery.state(record.sandbox_id)
            row.update(desired_state=state.get('desired_state', 'running'), last_operation=state.get('last_job'))
            if query.lower() not in ' '.join(str(row[k] or '') for k in ('sandbox_id', 'container_id', 'agent_id', 'username')).lower():
                continue
            if status and row['status'] != status:
                continue
            rows.append(row)
        rows.sort(key=lambda r: r['sandbox_id'])
        return {'items': rows[offset:offset + limit], 'total': len(rows), 'offset': offset, 'limit': limit,
                'sampled_at': time.time(), 'status_source': 'registry_health_monitor'}

    def submit(self, kind, target, request_id, revision=None, deletion_fingerprint=None, force=None):
        sid = target if kind.startswith('sandbox.') else None
        aid = self.find(sid).agent_id if sid else target
        with self.store.edit() as data:
            for job in data['jobs'].values():
                if job.get('request_id') == request_id:
                    if job['kind'] != kind or job['payload'].get('resource_id') != target:
                        fail('Request ID was already used for another operation', 409)
                    return job['id'], False
            load_tests = getattr(self.runtime, 'load_tests', None)
            if load_tests and load_tests.store.active_agent(aid):
                fail('Stop the active load test before changing this Agent or its sandboxes', 409)
            # Check revision inside the transaction, after idempotency lookup.
            if revision is not None:
                current, _ = self.store.read()
                if current != revision:
                    fail('Configuration changed; reload before operating', 409)
            agent = data['agents'].get(aid)
            if agent is None:
                fail('Agent not found', 404)
            if agent.get('lifecycle') == 'deleting' and kind != 'agent.delete':
                fail('Finish permanent deletion before using this Agent ID', 409)
            archived = agent.get('lifecycle') in {'archived', 'deleting'}
            if kind == 'agent.delete' and (not archived or not deletion_fingerprint):
                fail('Permanent deletion requires an archived Agent and current impact preview', 409)
            if kind in {'sandbox.start', 'sandbox.restart', 'sandbox.recover'} and archived:
                fail('Restore archived Agent first', 409)
            if kind == 'agent.restore' and not archived:
                fail('Agent is not archived', 409)
            if kind == 'agent.archive' and archived:
                fail('Agent is already archived', 409)
            if any(j['status'] in ACTIVE and j['target'] in {aid, '*'} for j in data['jobs'].values()):
                fail('Another operation affects this Agent; wait for it to finish', 409)
            if kind == 'agent.delete-empty':
                if agent['versions'] or any(r.agent_id == aid for r in self.backend.registry.list_sandboxes()) or any(r.get('owner') == aid for r in data['resources'].values()):
                    fail('Only an unpublished Agent without sandboxes or private resources can be deleted here', 409)
            jid = 'job_' + uuid.uuid4().hex
            if kind == 'agent.delete':
                agent['lifecycle'] = 'deleting'
            data['jobs'][jid] = {'id': jid, 'kind': kind, 'target': aid, 'request_id': request_id,
                'status': 'queued', 'created': time.time(), 'checkpoint': 'queued', 'payload': {'resource_id': target, 'deletion_fingerprint': deletion_fingerprint, 'force': force}, 'error': None}
            return jid, True

    def check_acquire(self, aid, username):
        _, data = self.store.read()
        record = self.backend.registry.get_sandbox(aid, username)
        if record and data.get('sandbox_operations', {}).get(record.sandbox_id, {}).get('desired_state') == 'stopped':
            fail('Sandbox was stopped manually; start it in sandbox management', 409)

    async def run(self, jid):
        async with self.runtime.lock:
            _, data = self.store.read()
            job = data['jobs'][jid]
            if job['status'] not in ACTIVE:
                return
            aid, kind = job['target'], job['kind']
            self.runtime.blocked.add(aid)
            try:
                self.store.job(jid, status='waiting')
                if kind == 'sandbox.recover':
                    record = self.find(job['payload']['resource_id'])
                    if not self.recovery.policy().enabled or not await self.recovery.idle_evidence(record):
                        fail('Automatic recovery skipped: execution is busy or unknown', 409)
                if job['payload'].get('force'):
                    force = job['payload']['force']
                    if force['fingerprint'] != self.details.fingerprint(job['payload']['resource_id']):
                        fail('Force operation impact changed before execution; preview again', 409)
                    self.store.job(jid, interrupted_sessions=force['sessions'])
                else:
                    await self.runtime.drain({aid})
                self.store.job(jid, status='applying')
                if kind.startswith('sandbox.'):
                    await self.sandbox_action(job)
                elif kind == 'agent.archive':
                    # Drain the entire Agent, then stop containers without removing data.
                    for record in await self.runtime.records({aid}):
                        container = await self.backend._get_container(record.container_id) if record.container_id else None
                        if container:
                            self.backend._verify_ownership(container, aid, record.username)
                            await asyncio.to_thread(container.stop, timeout=10)
                            await asyncio.to_thread(self.backend.registry.set_health_status, record.sandbox_id, 'stopped')
                    with self.store.edit() as updated:
                        updated['agents'][aid]['lifecycle'] = 'archived'
                elif kind == 'agent.restore':
                    with self.store.edit() as updated:
                        updated['agents'][aid]['lifecycle'] = 'active'
                elif kind == 'agent.delete':
                    await self.runtime.remove_sandboxes({aid})
                    await asyncio.to_thread(self.deletion.execute, aid, job['payload']['deletion_fingerprint'])
                elif kind == 'agent.delete-empty':
                    with self.store.edit() as updated:
                        agent = updated['agents'][aid]
                        if agent['versions'] or any(r.get('owner') == aid for r in updated['resources'].values()):
                            fail('Agent changed; reload before deleting', 409)
                        del updated['agents'][aid]
                        updated.setdefault('agent_tombstones', {})[aid] = {'deleted_at': time.time()}
                else:
                    fail('Unsupported operation')
                self.store.job(jid, status='succeeded', checkpoint='completed', result={'resource_id': job['payload']['resource_id']})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.store.job(jid, status='failed', error=exc.detail if isinstance(exc, HTTPException) else 'Operation failed; inspect sandbox status before retrying')
            finally:
                self.runtime.blocked.discard(aid)

    async def sandbox_action(self, job):
        sid = job['payload']['resource_id']
        record = self.find(sid)
        action = job['kind'].split('.')[1]
        container = await self.backend._get_container(record.container_id) if record.container_id else None
        if container:
            self.backend._verify_ownership(container, record.agent_id, record.username)
        # Persist manual intent before a start, so interrupted operations cannot be
        # interpreted as an automatic recovery request.
        with self.store.edit() as data:
            data.setdefault('sandbox_operations', {})[sid] = {
                'desired_state': 'running' if action == 'recover' else 'stopped', 'last_job': job['id']}
        checkpoint = self.store.read()[1]['jobs'][job['id']].get('checkpoint')
        if action in {'stop', 'restart', 'recover'} and container and checkpoint not in {'stopped', 'start_requested'}:
            self.store.job(job['id'], checkpoint='stop_requested', old_container=record.container_id)
            await asyncio.to_thread(container.stop, timeout=10)
            await asyncio.to_thread(self.backend.registry.set_health_status, sid, 'stopped')
            self.store.job(job['id'], checkpoint='stopped')
        if action in {'start', 'restart', 'recover'}:
            self.store.job(job['id'], checkpoint='start_requested')
            key = (record.agent_id, record.username)
            lock = self.backend._locks.setdefault(key, asyncio.Lock())
            async with lock:
                # Normal provisioning preserves session state and workspace mounts.
                await self.backend._acquire_locked(*key)
            with self.store.edit() as data:
                data['sandbox_operations'][sid]['desired_state'] = 'running'
        else:
            await asyncio.to_thread(self.backend.registry.set_health_status, sid, 'stopped')
        self.store.job(job['id'], checkpoint='completed')

    async def reconcile(self, jid):
        """Recover only when actual state makes the next effect unambiguous."""
        job = self.store.read()[1]['jobs'][jid]
        checkpoint, kind = job.get('checkpoint'), job['kind']
        if checkpoint == 'completed':
            self.store.job(jid, status='succeeded', recovered=True)
            return
        if kind.startswith('sandbox.'):
            record = self.find(job['payload']['resource_id'])
            container = await self.backend._get_container(record.container_id) if record.container_id else None
            if container:
                self.backend._verify_ownership(container, record.agent_id, record.username)
                await asyncio.to_thread(container.reload)
            stopped = not container or container.status in {'exited', 'dead', 'created'}
            if checkpoint == 'stop_requested' and stopped:
                self.store.job(jid, checkpoint='stopped', recovered=True)
                checkpoint = 'stopped'
            if checkpoint == 'start_requested' and not stopped:
                endpoint = await self.backend.inspect(record.agent_id, record.username)
                if endpoint:
                    with self.store.edit() as data:
                        data.setdefault('sandbox_operations', {}).setdefault(record.sandbox_id, {})['desired_state'] = 'running'
                    self.store.job(jid, status='succeeded', checkpoint='completed', recovered=True)
                    return
            if checkpoint in {'queued', 'stopped'} or (checkpoint == 'start_requested' and stopped):
                # Force confirmation is never silently reused after a restart.
                if not job['payload'].get('force'):
                    self.runtime.spawn(self.run(jid))
                    return
        if kind == 'agent.delete' and job['target'] not in self.store.read()[1]['agents']:
            self.store.job(jid, status='succeeded', checkpoint='completed', recovered=True)
            return
        agent = self.store.read()[1]['agents'].get(job['target'])
        complete = (kind == 'agent.archive' and agent and agent.get('lifecycle') == 'archived') or (kind == 'agent.restore' and agent and agent.get('lifecycle','active') == 'active') or (kind == 'agent.delete-empty' and agent is None)
        if complete:
            self.store.job(jid, status='succeeded', checkpoint='completed', recovered=True)
            return
        self.store.job(jid, status='failed', error='Controller restarted: actual state checked; operation outcome is ambiguous. Review and retry.', recovered=True)

