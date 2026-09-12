"""Bounded recovery decisions based on observed execution state, not SSE leases."""
import asyncio
import json
import time

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.session_binding import directory_collection


class RecoveryPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = True
    failure_threshold: int = Field(3, ge=1, le=20)
    max_attempts: int = Field(3, ge=1, le=10)
    window_seconds: int = Field(900, ge=60, le=86400)
    backoff_seconds: list[int] = Field(default_factory=lambda: [30, 60, 120], min_length=1, max_length=10)
    stable_seconds: int = Field(300, ge=30, le=3600)
    agent_enabled: dict[str, bool] = Field(default_factory=dict)
    max_parallel_recoveries: int = Field(2, ge=1, le=2)


class Recovery:
    def __init__(self, operations):
        self.ops = operations
        self.store = operations.store
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS recovery_state (sid TEXT PRIMARY KEY, document TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS recovery_policy (id INTEGER PRIMARY KEY, document TEXT NOT NULL)')

    def policy(self):
        with self.store.connect() as db:
            row = db.execute('SELECT document FROM recovery_policy WHERE id=1').fetchone()
        return RecoveryPolicy.model_validate_json(row[0]) if row else RecoveryPolicy()

    def save_policy(self, policy):
        if any(n < 1 or n > 3600 for n in policy.backoff_seconds):
            from app.management import fail
            fail('Recovery backoff must be between 1 and 3600 seconds')
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO recovery_policy VALUES (1,?)', (policy.model_dump_json(),))

    def state(self, sid):
        with self.store.connect() as db:
            row = db.execute('SELECT document FROM recovery_state WHERE sid=?', (sid,)).fetchone()
        return json.loads(row[0]) if row else {}

    def update(self, sid, **values):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT document FROM recovery_state WHERE sid=?', (sid,)).fetchone()
            state = json.loads(row[0]) if row else {}
            state.update(values)
            db.execute('INSERT OR REPLACE INTO recovery_state VALUES (?,?)', (sid, json.dumps(state)))
        return state

    def invalidate_idle(self, aid):
        for record in self.ops.backend.registry.list_sandboxes():
            if record.agent_id == aid:
                state = self.state(record.sandbox_id)
                self.update(record.sandbox_id, execution='unknown', healthy_since=None,
                            activity_generation=state.get('activity_generation', 0) + 1)

    async def idle_evidence(self, record):
        runtime = self.ops.runtime
        generation = self.state(record.sandbox_id).get('activity_generation', 0)
        if runtime.requests.get(record.agent_id, 0) or runtime.acquiring.get(record.agent_id, 0):
            return False
        endpoint = await self.ops.backend.inspect(record.agent_id, record.username)
        if endpoint:
            try:
                states = await directory_collection(runtime.client, self.ops.backend.registry, endpoint, timeout=2)
                if (runtime.requests.get(record.agent_id, 0) or runtime.acquiring.get(record.agent_id, 0)
                        or generation != self.state(record.sandbox_id).get('activity_generation', 0)):
                    return False
                idle = isinstance(states, dict) and all(s.get('type') == 'idle' for s in states.values())
                self.update(record.sandbox_id, execution='idle' if idle else 'busy', container_id=record.container_id)
                return idle
            except Exception:
                return False
        # Native async work invalidates this evidence before forwarding a request.
        state = self.state(record.sandbox_id)
        return state.get('execution') == 'idle' and state.get('container_id') == record.container_id

    async def tick(self, dependencies_healthy=True, health_failures=None):
        policy = self.policy()
        if not policy.enabled or not dependencies_healthy:
            return
        try:
            if not await asyncio.to_thread(self.ops.backend.client.ping):
                return
        except Exception:
            return
        for record in self.ops.backend.registry.list_sandboxes():
            load_tests = getattr(self.ops.runtime, 'load_tests', None)
            if load_tests and load_tests.owns_user(record.username):
                continue  # Recovery must not conceal test failures or recreate test users.
            if not record.container_id:
                continue  # Includes deliberate idle evictions.
            if not policy.agent_enabled.get(record.agent_id, True):
                continue
            _, catalog = self.store.read()
            agent = catalog['agents'].get(record.agent_id, {})
            desired = catalog.get('sandbox_operations', {}).get(record.sandbox_id, {}).get('desired_state')
            if desired == 'stopped' or agent.get('lifecycle') in {'archived', 'deleting'} or record.agent_id in self.ops.runtime.blocked:
                continue
            state, now = self.state(record.sandbox_id), time.time()
            if record.status == 'ready':
                # Idle observation is independent of request/SSE lifetime.
                await self.idle_evidence(record)
                since = state.get('healthy_since') or now
                values = {'failures': 0, 'healthy_since': since, 'reason': None}
                if now - since >= policy.stable_seconds:
                    values.update(attempts=[], next_attempt=0)
                self.update(record.sandbox_id, **values)
                continue
            if record.status not in {'unhealthy', 'missing'}:
                continue
            failures = max(state.get('failures', 0) + 1, (health_failures or {}).get(record.sandbox_id, 0))
            self.update(record.sandbox_id, failures=failures, healthy_since=None)
            if failures < policy.failure_threshold or now < state.get('next_attempt', 0):
                continue
            attempts = [t for t in state.get('attempts', []) if now - t < policy.window_seconds]
            if len(attempts) >= policy.max_attempts:
                self.update(record.sandbox_id, reason='Recovery limit reached; manual intervention required')
                continue
            if not await self.idle_evidence(record):
                self.update(record.sandbox_id, reason='Execution is busy or unknown; automatic restart skipped')
                continue
            try:
                jid, created = self.ops.submit('sandbox.recover', record.sandbox_id, 'recovery-' + str(time.time_ns()))
            except HTTPException:
                continue
            if created:
                delay = policy.backoff_seconds[min(len(attempts), len(policy.backoff_seconds) - 1)]
                self.update(record.sandbox_id, attempts=attempts + [now], next_attempt=now + delay, reason='Recovery queued')
                self.ops.runtime.spawn(self.ops.run(jid))
