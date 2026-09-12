"""Durable load-test ownership and reports, separate from configuration revisions."""
import csv
import hashlib
import io
import json
import math
import time
import uuid

from pydantic import Field, model_validator

from app.admin_dto import DTO, ResourceID
from app.management import fail

ACTIVE = {'queued', 'preparing', 'running', 'cancelling'}
PREFIX = 'loadtest-'
PROMPT = 'This is a load test. Do not use tools, ask questions, or request permission. Reply with exactly: LOAD-TEST-OK'


class LoadAgent(DTO):
    agent_id: ResourceID
    users: int = Field(1, ge=1, le=100)
    cpu_limit: float = Field(1, ge=.25, le=64, allow_inf_nan=False)
    memory_mb: int = Field(1024, ge=256, le=65536)


class LoadRequest(DTO):
    request_id: str = Field(min_length=8, max_length=128)
    agents: list[LoadAgent] = Field(min_length=1, max_length=32)
    timeout_seconds: int = Field(180, ge=10, le=1800)
    prepare_timeout_seconds: int = Field(120, ge=10, le=300)

    @model_validator(mode='after')
    def bounds(self):
        if sum(a.users for a in self.agents) > 100:
            raise ValueError('At most 100 users per test')
        if len({a.agent_id for a in self.agents}) != len(self.agents):
            raise ValueError('Select each Agent only once')
        return self


def summarize(users):
    successful = [u for u in users if u['phase'] == 'succeeded']
    latencies = sorted(u['latency_ms'] for u in successful)
    starts = [u['sent_at'] for u in users if u.get('sent_at') is not None]
    ends = [u['finished_at'] for u in users if u.get('sent_at') is not None and u.get('finished_at')]
    elapsed = max(ends) - min(starts) if starts and ends else 0
    def percentile(p):
        return round(latencies[max(0, math.ceil(len(latencies) * p) - 1)], 2) if latencies else None
    return {'users': len(users), 'prepared': sum(bool(u.get('session_id')) for u in users),
        'submitted': len(starts), 'succeeded': len(successful),
        'failed': sum(u['phase'] in {'prepare_failed', 'failed', 'timed_out', 'interrupted'} for u in users),
        'cancelled': sum(u['phase'] == 'cancelled' for u in users),
        'success_rate': len(successful) / len(users) if users else 0,
        'p50_ms': percentile(.5), 'p95_ms': percentile(.95), 'p99_ms': percentile(.99),
        'mean_ms': round(sum(latencies) / len(latencies), 2) if latencies else None,
        'launch_spread_ms': round((max(starts) - min(starts)) * 1000, 2) if starts else None,
        'generation_seconds': round(elapsed, 3),
        'successful_requests_per_second': round(len(successful) / elapsed, 4) if elapsed > 0 else 0,
        'input_tokens': sum(u.get('input_tokens', 0) for u in users),
        'output_tokens': sum(u.get('output_tokens', 0) for u in users)}


class LoadTestStore:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS load_tests (id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL, document TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS load_test_users (username TEXT PRIMARY KEY, agent_id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES load_tests(id), state TEXT NOT NULL, document TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS load_test_users_run ON load_test_users(run_id)')

    def validate_agents(self, request):
        _, catalog = self.store.read()
        snapshots = {}
        for selected in request.agents:
            agent = catalog['agents'].get(selected.agent_id)
            config = self.store.agent_config(agent) if agent else None
            if not config or not config.get('enabled', True) or agent.get('lifecycle', 'active') != 'active':
                fail('Select an existing, published and enabled Agent: ' + selected.agent_id, 409)
            snapshots[selected.agent_id] = {'version': agent['active'], 'model_id': config['default_model_id']}
        return snapshots

    def create(self, request):
        payload = request.model_dump()
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.store.lock, self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT id,fingerprint FROM load_tests WHERE request_id=?', (request.request_id,)).fetchone()
            if previous:
                if previous[1] != fingerprint:
                    fail('Request ID was already used with different test parameters', 409)
                return previous[0], False
            placeholders = ','.join('?' for _ in ACTIVE)
            if db.execute(f'SELECT 1 FROM load_tests WHERE status IN ({placeholders})', tuple(ACTIVE)).fetchone():
                fail('A load test is already active', 409)
            snapshots = self.validate_agents(request)
            rid = 'lt_' + uuid.uuid4().hex
            now = time.time()
            document = {'id': rid, 'request': payload, 'snapshots': snapshots, 'prompt': PROMPT,
                        'created_at': now, 'cleanup_status': 'retained', 'scope': 'server_initiated_controller_sandbox_model'}
            db.execute('INSERT INTO load_tests VALUES (?,?,?,?,?,?)', (rid, request.request_id, fingerprint, 'queued', now, json.dumps(document)))
            index = 0
            for agent in request.agents:
                for _ in range(agent.users):
                    index += 1
                    username = PREFIX + rid[3:] + '-' + str(index)
                    user = {'username': username, 'agent_id': agent.agent_id, 'run_id': rid,
                            'cpu_limit': agent.cpu_limit, 'memory_mb': agent.memory_mb, 'phase': 'queued'}
                    db.execute('INSERT INTO load_test_users VALUES (?,?,?,?,?)', (username, agent.agent_id, rid, 'retained', json.dumps(user)))
            return rid, True

    def previous(self, request):
        fingerprint = hashlib.sha256(json.dumps(request.model_dump(), sort_keys=True).encode()).hexdigest()
        with self.store.connect() as db:
            row = db.execute('SELECT id,fingerprint FROM load_tests WHERE request_id=?', (request.request_id,)).fetchone()
        if row and row[1] != fingerprint:
            fail('Request ID was already used with different test parameters', 409)
        return row[0] if row else None

    def get(self, rid):
        with self.store.connect() as db:
            row = db.execute('SELECT status,document FROM load_tests WHERE id=?', (rid,)).fetchone()
            if not row:
                fail('Load test not found', 404)
            users = [dict(json.loads(r[1]), storage_state=r[0]) for r in db.execute('SELECT state,document FROM load_test_users WHERE run_id=? ORDER BY username', (rid,))]
        report = dict(json.loads(row[1]), status=row[0], users=users)
        report['summary'] = summarize(users)
        report['by_agent'] = {aid: summarize([u for u in users if u['agent_id'] == aid]) for aid in report['snapshots']}
        return report

    def list(self, offset=0, limit=25):
        with self.store.connect() as db:
            total = db.execute('SELECT count(*) FROM load_tests').fetchone()[0]
            rows = db.execute('SELECT id,status,document FROM load_tests ORDER BY created_at DESC LIMIT ? OFFSET ?', (limit, offset)).fetchall()
            placeholders = ','.join('?' for _ in ACTIVE)
            active = db.execute(f'SELECT id FROM load_tests WHERE status IN ({placeholders}) LIMIT 1', tuple(ACTIVE)).fetchone()
        return {'total': total, 'offset': offset, 'limit': limit,
                'active_id': active[0] if active else None,
                'items': [dict(json.loads(r[2]), status=r[1]) for r in rows]}

    def active_user(self, aid, username):
        if not username.startswith(PREFIX):
            return False
        with self.store.connect() as db:
            row = db.execute('SELECT r.status,r.document FROM load_test_users u JOIN load_tests r ON r.id=u.run_id WHERE u.username=? AND u.agent_id=?', (username, aid)).fetchone()
        return bool(row and (row[0] in ACTIVE or json.loads(row[1])['cleanup_status'] == 'cleaning'))

    def active_agent(self, aid):
        with self.store.connect() as db:
            placeholders = ','.join('?' for _ in ACTIVE)
            row = db.execute(f'SELECT 1 FROM load_test_users u JOIN load_tests r ON r.id=u.run_id WHERE u.agent_id=? AND r.status IN ({placeholders}) LIMIT 1', (aid, *ACTIVE)).fetchone()
        return row is not None

    def update(self, rid, **values):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status,document FROM load_tests WHERE id=?', (rid,)).fetchone()
            if not row:
                fail('Load test not found', 404)
            status = values.pop('status', row[0])
            document = dict(json.loads(row[1]), **values)
            db.execute('UPDATE load_tests SET status=?,document=? WHERE id=?', (status, json.dumps(document), rid))

    def user(self, agent_id, username):
        if not username.startswith(PREFIX):
            return None
        with self.store.connect() as db:
            row = db.execute('SELECT state,document FROM load_test_users WHERE username=? AND agent_id=?', (username, agent_id)).fetchone()
        return dict(json.loads(row[1]), storage_state=row[0]) if row else None

    def update_user(self, username, **values):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT state,document FROM load_test_users WHERE username=?', (username,)).fetchone()
            if not row:
                fail('Load test user not found', 404)
            state = values.pop('storage_state', row[0])
            db.execute('UPDATE load_test_users SET state=?,document=? WHERE username=?',
                       (state, json.dumps(dict(json.loads(row[1]), **values)), username))

    def recover(self):
        with self.store.connect() as db:
            ids = [row[0] for row in db.execute('SELECT id FROM load_tests')]
        for rid in ids:
            report = self.get(rid)
            if report['status'] in ACTIVE:
                self.update(rid, status='interrupted', finished_at=time.time(), error='Controller restarted; requests were not replayed')
                for user in report['users']:
                    if user['phase'] in {'queued', 'preparing', 'ready', 'running'}:
                        self.update_user(user['username'], phase='interrupted', finished_at=time.time(), error='CONTROLLER_RESTARTED')
            if report['cleanup_status'] == 'cleaning':
                self.update(rid, cleanup_status='failed', cleanup_error='Controller restarted; retry cleanup')


def report_csv(report):
    output = io.StringIO(newline='')
    fields = ['agent_id', 'username', 'sandbox_id', 'session_id', 'cpu_limit', 'memory_mb', 'phase',
              'prepare_ms', 'sent_at', 'latency_ms', 'input_tokens', 'output_tokens', 'error', 'storage_state']
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for user in report['users']:
        writer.writerow({key: ("'" + str(value) if isinstance(value, str) and value.startswith(('=', '+', '-', '@')) else value)
                         for key, value in user.items() if key in fields})
    return '\ufeff' + output.getvalue()
