"""Explicit impact previews and bounded deletion of an archived Agent's owned data."""
import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path

from app.management import fail, identifier


class AgentDeletion:
    def __init__(self, operations):
        self.ops, self.store = operations, operations.store
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS agent_delete_previews (id TEXT PRIMARY KEY, expires REAL, document TEXT)')

    def roots(self, aid, agent):
        roots = []
        for base in (self.ops.backend.workspaces.workspace_root, self.ops.backend.workspaces.state_root):
            base = Path(base).resolve(strict=True)
            target = base / identifier(aid)
            if target.is_symlink() or target.resolve().parent != base:
                fail('Agent data path changed; inspect storage before deleting', 409)
            roots.append(target)
        compiled = (self.store.root / 'compiled').resolve()
        for version in agent['versions']:
            target = Path(version['path'])
            # Original packaged Agent definitions are read-only deployment templates.
            if target.is_relative_to(compiled):
                if target.is_symlink() or not target.resolve().is_relative_to(compiled) or target.name != aid:
                    fail('Compiled configuration path changed', 409)
                roots.append(target)
        return list(dict.fromkeys(roots))

    def impact(self, aid):
        revision, data = self.store.read()
        agent = data['agents'].get(aid)
        if agent is None:
            fail('Agent not found', 404)
        records = [r for r in self.ops.backend.registry.list_sandboxes() if r.agent_id == aid]
        files, total = [], 0
        for root in self.roots(aid, agent):
            if not root.exists():
                continue
            for path in root.rglob('*'):
                if path.is_symlink():
                    fail('Agent data contains symbolic links; remove them before permanent deletion', 409)
                if path.is_file():
                    stat = path.stat()
                    total += stat.st_size
                    files.append((str(path), stat.st_size, stat.st_mtime_ns))
                if len(files) > 100000:
                    fail('Deletion preview exceeds 100000 files', 413)
        private = sorted(rid for rid, r in data['resources'].items() if r.get('owner') == aid)
        with self.ops.backend.registry.connect() as db:
            sessions = db.execute('SELECT COUNT(*) FROM sessions WHERE agent_id=?', (aid,)).fetchone()[0]
        fingerprint = hashlib.sha256(json.dumps({'files': sorted(files), 'agent': {k: v for k, v in agent.items() if k != 'lifecycle'},
            'sandboxes': sorted(r.sandbox_id for r in records), 'private_resources': {rid: data['resources'][rid] for rid in private}}, sort_keys=True).encode()).hexdigest()
        return {'agent_id': aid, 'revision': revision, 'lifecycle': agent.get('lifecycle', 'active'),
                'sandboxes': [r.sandbox_id for r in records], 'sessions': sessions,
                'files': len(files), 'bytes': total, 'private_resources': private, 'fingerprint': fingerprint,
                'warning': 'Permanently deletes this Agent configuration history, sessions, workspace and private resources. Global resources are retained.'}

    def preview(self, aid):
        impact = self.impact(aid)
        token = 'delete_' + uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute('DELETE FROM agent_delete_previews WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO agent_delete_previews VALUES (?,?,?)', (token, time.time() + 300, json.dumps(impact)))
        return {**impact, 'preview_id': token}

    def authorize(self, aid, token, confirmation):
        if confirmation != aid:
            fail('Type the exact Agent ID to confirm permanent deletion')
        with self.store.connect() as db:
            row = db.execute('SELECT expires,document FROM agent_delete_previews WHERE id=?', (token,)).fetchone()
        if not row or row[0] < time.time():
            fail('Deletion preview expired', 409)
        previous, current = json.loads(row[1]), self.impact(aid)
        if previous['agent_id'] != aid or previous['fingerprint'] != current['fingerprint'] or previous['revision'] != current['revision']:
            fail('Deletion impact changed; preview again', 409)
        if current['lifecycle'] not in {'archived', 'deleting'}:
            fail('Archive the Agent before permanent deletion', 409)
        return current

    def execute(self, aid, expected):
        impact = self.impact(aid)
        if impact['fingerprint'] != expected:
            fail('Deletion impact changed; preview again', 409)
        _, data = self.store.read()
        for root in self.roots(aid, data['agents'][aid]):
            if root.exists():
                shutil.rmtree(root)
        # Both phases are idempotent. If interrupted, Agent remains deleting and
        # cannot execute until the administrator reviews and retries the operation.
        with self.ops.backend.registry.connect() as db:
            db.execute('DELETE FROM sessions WHERE agent_id=?', (aid,))
            db.execute('DELETE FROM sandboxes WHERE agent_id=?', (aid,))
            db.execute('DELETE FROM agents WHERE agent_id=?', (aid,))
        with self.store.edit() as updated:
            updated['resources'] = {rid: r for rid, r in updated['resources'].items() if r.get('owner') != aid}
            updated['agents'].pop(aid, None)
            updated.setdefault('agent_tombstones', {})[aid] = {'deleted_at': time.time()}
        # Shared content-addressed blobs are retained for separate garbage collection.
