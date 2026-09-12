"""Read-only sandbox diagnostics and expiring force-operation impact snapshots."""
import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import asdict

from app.management import fail
from app.session_binding import directory_collection


class SandboxDetails:
    def __init__(self, operations):
        self.ops = operations
        with operations.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS operation_previews(id TEXT PRIMARY KEY, expires REAL, document TEXT)')

    async def detail(self, sid):
        record = self.ops.find(sid)
        backend, runtime = self.ops.backend, self.ops.runtime
        _, catalog = self.ops.store.read()
        sessions = [asdict(s) for s in backend.registry.list_sessions_for_sandbox(sid)]
        result = {**asdict(record), 'sampled_at': time.time(), 'container_state': 'unknown',
                  'cpu_percent': None, 'memory_bytes': None, 'memory_limit': None,
                  'execution': 'unknown', 'sessions': sessions,
                  'configuration_version': catalog['agents'][record.agent_id]['active'],
                  'recovery': self.ops.recovery.state(sid),
                  'operations': sorted([j for j in catalog['jobs'].values() if j['payload'].get('resource_id') == sid], key=lambda j:j['created'], reverse=True)[:20]}
        container = await backend._get_container(record.container_id) if record.container_id else None
        if not container:
            result['container_state'] = 'absent'
            return result
        backend._verify_ownership(container, record.agent_id, record.username)
        try:
            await asyncio.to_thread(container.reload)
            result['container_state'] = container.status
            labels = container.attrs.get('Config', {}).get('Labels', {}) or {}
            result['container_configuration'] = labels.get('cloud.config_version')
            if container.status == 'running':
                stats = await asyncio.wait_for(asyncio.to_thread(container.stats, stream=False), 5)
                cpu, previous = stats.get('cpu_stats', {}), stats.get('precpu_stats', {})
                delta = cpu.get('cpu_usage', {}).get('total_usage', 0) - previous.get('cpu_usage', {}).get('total_usage', 0)
                system = cpu.get('system_cpu_usage', 0) - previous.get('system_cpu_usage', 0)
                if system > 0 and delta >= 0:
                    result['cpu_percent'] = round(delta / system * cpu.get('online_cpus', 1) * 100, 2)
                result.update(memory_bytes=stats.get('memory_stats', {}).get('usage'), memory_limit=stats.get('memory_stats', {}).get('limit'))
                endpoint = await backend.inspect(record.agent_id, record.username)
                if endpoint:
                    states = await directory_collection(runtime.client, backend.registry, endpoint, timeout=2)
                    result['execution'] = 'busy' if any(s.get('type') != 'idle' for s in states.values()) else 'idle'
                    for session in sessions:
                        session['execution'] = states.get(session['session_id'], {'type':'idle'})
        except Exception:
            result['diagnostic_error'] = 'Some diagnostics could not be sampled; unknown is not idle'
        return result

    def fingerprint(self, sid):
        record = self.ops.find(sid)
        sessions = sorted(s.session_id for s in self.ops.backend.registry.list_sessions_for_sandbox(sid))
        generation = self.ops.recovery.state(sid).get('activity_generation', 0)
        return hashlib.sha256(json.dumps([record.container_id, sessions, generation]).encode()).hexdigest()

    async def preview(self, sid):
        detail = await self.detail(sid)
        token = 'force_' + uuid.uuid4().hex
        result = {'sandbox_id': sid, 'preview_id': token, 'fingerprint': self.fingerprint(sid),
                  'sessions': [s['session_id'] for s in detail['sessions']], 'execution': detail['execution']}
        with self.ops.store.connect() as db:
            db.execute('DELETE FROM operation_previews WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO operation_previews VALUES (?,?,?)', (token, time.time()+300, json.dumps(result)))
        return result

    def authorize(self, sid, token, confirmation):
        with self.ops.store.connect() as db:
            row = db.execute('SELECT expires,document FROM operation_previews WHERE id=?', (token,)).fetchone()
        if confirmation != sid or not row or row[0] < time.time():
            fail('Force operation needs a current preview and exact sandbox ID confirmation', 409)
        value = json.loads(row[1])
        if value['sandbox_id'] != sid or value['fingerprint'] != self.fingerprint(sid):
            fail('Affected sessions changed; preview the force operation again', 409)
        return value
