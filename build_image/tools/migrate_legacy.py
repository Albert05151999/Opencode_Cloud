#!/usr/bin/env python3
"""Offline, source-preserving migration from monolith data to service-owned data."""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time

ACTIVE = {'queued', 'validating', 'preparing', 'running', 'waiting', 'applying', 'cancelling'}
OPS_SCHEMA = '''CREATE TABLE jobs (id TEXT PRIMARY KEY, request_id TEXT UNIQUE, target TEXT, document TEXT);
CREATE TABLE state (key TEXT PRIMARY KEY, document TEXT);
CREATE TABLE load_tests (id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL, document TEXT NOT NULL);
CREATE TABLE load_test_users (username TEXT PRIMARY KEY, agent_id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES load_tests(id), state TEXT NOT NULL, document TEXT NOT NULL);
CREATE INDEX load_test_users_run ON load_test_users(run_id);'''


def safe_copy(source, target):
    source = Path(source)
    if source.is_symlink() or (source.is_dir() and any(p.is_symlink() for p in source.rglob('*'))):
        raise ValueError(f'Symlink input requires explicit operator handling: {source}')
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir(): shutil.copytree(source, target)
    else: shutil.copy2(source, target)


def snapshot_db(source, target):
    """Read source files only; SQLite opens a disposable copy so WAL/SHM never touch source."""
    with tempfile.TemporaryDirectory(prefix='cloud-migration-snapshot-') as directory:
        temporary = Path(directory) / 'database.db'
        safe_copy(source, temporary)
        for suffix in ('-wal', '-shm'):
            companion = Path(str(source) + suffix)
            if companion.exists(): safe_copy(companion, Path(str(temporary) + suffix))
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(temporary) as incoming, sqlite3.connect(target) as outgoing:
            if incoming.execute('PRAGMA quick_check').fetchone()[0] != 'ok': raise ValueError('Source database integrity check failed')
            incoming.backup(outgoing)


def remap(value, paths):
    if isinstance(value, dict): return {key: remap(item, paths) for key,item in value.items()}
    if isinstance(value, list): return [remap(item, paths) for item in value]
    if isinstance(value, str):
        for old,new in paths:
            if value == old or value.startswith(old + '/'):
                return new + value[len(old):]
    return value


def table_exists(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def migrate(source, destination, *, apply=False, services_stopped=False, copy_workspaces=False):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_dir(): raise ValueError('Source deployment data directory does not exist')
    if source == destination or source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError('Source and destination must be separate, non-overlapping directories')
    if destination.exists() and any(destination.iterdir()): raise ValueError('Destination must be absent or empty; existing data is never merged or overwritten')
    if apply and not services_stopped: raise ValueError('--apply requires --services-stopped after stopping old and new services and sandboxes')
    catalog_source = source / 'management/catalog.db'
    if not catalog_source.exists(): raise ValueError('Expected legacy management/catalog.db')
    workspace = destination / 'workspaces' if copy_workspaces else source / 'workspaces'
    state = destination / 'file_service/state' if copy_workspaces else source / 'state'
    paths = [(str(source / 'management'), str(destination / 'catalog_service')),
             (str(source / 'workspaces'), str(workspace)), (str(source / 'state'), str(state))]
    report = {'schema_version':1, 'mode':'apply' if apply else 'dry-run', 'source':str(source), 'destination':str(destination),
              'source_unchanged':True, 'copy_workspaces':copy_workspaces, 'paths':dict(paths), 'jobs':0, 'jobs_needing_recovery':0,
              'limits':['No containers are restarted or replayed; operator must inspect migrated recovery jobs before admitting traffic.',
                        'Existing model gateway active configuration must be explicitly published through operations after migration.',
                        'External paths outside the selected source root are preserved; operator must provide matching mounts.',
                        'Destination runtime images/credentials and existing Docker containers must be reconciled before starting sandbox manager.']}
    # Dry-run may use disposable temp snapshots; it does not create or alter deployment directories.
    with tempfile.TemporaryDirectory(prefix='cloud-migration-review-') as directory:
        scratch = Path(directory)
        snapshot_db(catalog_source, scratch / 'catalog.db')
        sandbox_agents = {}
        if (source / 'platform.db').exists():
            snapshot_db(source / 'platform.db', scratch / 'platform.db')
            with sqlite3.connect(scratch / 'platform.db') as registry:
                if table_exists(registry, 'sandboxes'):
                    sandbox_agents = dict(registry.execute('SELECT sandbox_id,agent_id FROM sandboxes'))
        with sqlite3.connect(scratch / 'catalog.db') as db:
            row = db.execute('SELECT revision,document FROM catalog WHERE id=1').fetchone()
            if not row: raise ValueError('Legacy catalog row missing')
            if db.execute('PRAGMA user_version').fetchone()[0] > 1: raise ValueError('Unsupported newer catalog schema')
            revision, document = row[0], json.loads(row[1])
        jobs = document.pop('jobs', {})
        if not isinstance(jobs, dict): raise ValueError('Legacy jobs must be a mapping')
        report['jobs'] = len(jobs)
        report['jobs_needing_recovery'] = sum(job.get('status') in ACTIVE for job in jobs.values())
        report['catalog_revision'] = revision
        report['catalog_agents'] = len(document.get('agents', {}))
        report['unhandled_source_entries'] = sorted(p.name for p in source.iterdir() if p.name not in {'management', 'platform.db', 'platform.db-wal', 'platform.db-shm', 'workspaces', 'state'})
        if not apply: return report
        destination.parent.mkdir(parents=True,exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f'.{destination.name}-migration-',dir=destination.parent))
        try:
            staging.chmod(0o700)
            backup = staging / 'migration-backup'
            # Back up all management assets and source database files before any conversion.
            safe_copy(source / 'management', backup / 'management')
            for suffix in ('', '-wal', '-shm'):
                path = source / ('platform.db' + suffix)
                if path.exists(): safe_copy(path, backup / path.name)
            catalog_root = staging / 'catalog_service'; catalog_root.mkdir()
            shutil.copy2(scratch / 'catalog.db', catalog_root / 'catalog.db')
            for name in ('blobs', 'compiled'):
                path = source / 'management' / name
                if path.exists(): safe_copy(path, catalog_root / name)
            with sqlite3.connect(catalog_root / 'catalog.db') as db:
                db.execute('UPDATE catalog SET document=? WHERE id=1', (json.dumps(remap(document, paths)),))
            operations_root = staging / 'operations'; operations_root.mkdir()
            with sqlite3.connect(operations_root / 'operations.db') as ops, sqlite3.connect(scratch / 'catalog.db') as old:
                ops.executescript(OPS_SCHEMA)
                for jid, original in jobs.items():
                    job = remap(copy.deepcopy(original), paths)
                    job.update(id=jid, request_id='legacy:'+jid, scope=job.get('target','*'), target=job.get('target','*'),
                               checkpoint='legacy_import', updated=time.time(), migration={'previous_status':job.get('status'), 'automatic_replay':False})
                    job.setdefault('kind','legacy.unknown'); job.setdefault('payload',{}); job.setdefault('created',time.time())
                    if job['kind'].startswith('sandbox.'):
                        sid = job['payload'].get('resource_id', job['target'])
                        job['scope'] = sandbox_agents.get(sid, '*')  # Unknown ownership blocks all targets until reviewed.
                    if job.get('status') in ACTIVE:
                        job.update(status='needs_recovery', error='Interrupted by offline module migration; inspect legacy payload and existing containers before explicit recovery')
                    ops.execute('INSERT INTO jobs VALUES (?,?,?,?)',(jid,job['request_id'],job['target'],json.dumps(job)))
                for table in ('load_tests', 'load_test_users'):
                    if not table_exists(old,table): continue
                    columns = [row[1] for row in old.execute(f'PRAGMA table_info({table})')]
                    expected = [row[1] for row in ops.execute(f'PRAGMA table_info({table})')]
                    if columns != expected: raise ValueError(f'Unsupported {table} schema')
                    for row in old.execute(f'SELECT * FROM {table}'):
                        value = dict(zip(columns,row)); data = remap(json.loads(value['document']),paths)
                        if table == 'load_tests' and value['status'] in ACTIVE:
                            value['status'] = 'interrupted'; data.update(status='interrupted', migration={'automatic_replay':False})
                        value['document'] = json.dumps(data)
                        ops.execute(f'INSERT INTO {table} VALUES ({",".join("?" for _ in columns)})',tuple(value[key] for key in columns))
                for table,key_field,prefix in (('recovery_state','sandbox_id','recovery:'), ('recovery_policy','id','recovery-policy')):
                    if not table_exists(old,table): continue
                    columns = [row[1] for row in old.execute(f'PRAGMA table_info({table})')]
                    for row in old.execute(f'SELECT * FROM {table}'):
                        value = dict(zip(columns,row)); key = prefix + str(value.get(key_field,value.get('sid',''))) if prefix.endswith(':') else prefix
                        ops.execute('INSERT OR REPLACE INTO state VALUES (?,?)',(key,json.dumps(remap(json.loads(value['document']),paths))))
            with sqlite3.connect(catalog_root / 'catalog.db') as db:
                for table in ('load_test_users','load_tests','recovery_state','recovery_policy'): db.execute(f'DROP TABLE IF EXISTS {table}')
            platform = source / 'platform.db'
            if platform.exists():
                target = staging / 'sandbox_manager/platform.db'; target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(scratch / 'platform.db', target)
                compiled_source = source / 'management/compiled'
                compiled_target = destination / 'sandbox_manager/agents/legacy_compiled'
                registry_paths = [(str(compiled_source), str(compiled_target)), *paths]
                if compiled_source.exists(): safe_copy(compiled_source, staging / 'sandbox_manager/agents/legacy_compiled')
                with sqlite3.connect(target) as db:
                    if table_exists(db,'agents'):
                        for aid, path in db.execute('SELECT agent_id,config_path FROM agents').fetchall():
                            db.execute('UPDATE agents SET config_path=? WHERE agent_id=?',(remap(path,registry_paths),aid))
            if copy_workspaces:
                for old,new in ((source / 'workspaces',staging / 'workspaces'),(source / 'state',staging / 'file_service/state')):
                    if old.exists(): safe_copy(old,new)
            report['runtime_overrides'] = {'WORKSPACE_ROOT':str(workspace),'STATE_ROOT':str(state),'AGENTS_ROOT':str(destination / 'sandbox_manager/agents')}
            (staging / 'migration-report.json').write_text(json.dumps(report,indent=2)+'\n')
            for db in staging.rglob('*.db'): db.chmod(0o600)
            if destination.exists(): destination.rmdir()  # only the checked empty directory
            staging.rename(destination)
        except Exception:
            shutil.rmtree(staging)
            raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='default: inspect only')
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--services-stopped', action='store_true', help='confirm old/new services AND sandboxes have been stopped')
    parser.add_argument('--copy-workspaces', action='store_true', help='explicitly copy workspaces/state; default preserves source paths')
    args = parser.parse_args()
    try: result = migrate(args.source,args.destination,apply=args.apply,services_stopped=args.services_stopped,copy_workspaces=args.copy_workspaces)
    except (ValueError,sqlite3.Error,OSError) as error: parser.exit(1,str(error)+'\n')
    print(json.dumps(result,indent=2))

if __name__ == '__main__': main()
