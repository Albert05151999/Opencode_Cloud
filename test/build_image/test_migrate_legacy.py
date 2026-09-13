import hashlib
import json
from pathlib import Path
import sqlite3
import pytest
from build_image.tools.migrate_legacy import migrate


def legacy(tmp_path):
    root = tmp_path / 'old'; (root / 'management/blobs').mkdir(parents=True)
    (root / 'management/blobs/blob').write_bytes(b'preserved resource')
    (root / 'management/compiled/v1/agent').mkdir(parents=True)
    (root / 'management/compiled/v1/agent/config.json').write_text('{}')
    for name in ('workspaces','state'):
        (root / name).mkdir(); (root / name / 'kept').write_text(name)
    document = {'models':{},'resources':{},'agents':{'agent':{'active':1,'compiled':str(root / 'management/compiled/v1/agent')}},
                'jobs':{'job_old':{'id':'job_old','kind':'agent.apply','target':'agent','status':'applying','created':1,'payload':{'secret':'retained-in-db-only'}},
                        'job_done':{'id':'job_done','kind':'models.apply','target':'*','status':'succeeded','created':2,'result':{'version':3}}}}
    with sqlite3.connect(root / 'management/catalog.db') as db:
        db.execute('CREATE TABLE catalog (id INTEGER PRIMARY KEY,revision INTEGER,document TEXT)')
        db.execute('INSERT INTO catalog VALUES (1,7,?)',(json.dumps(document),))
        db.execute('CREATE TABLE recovery_state (sid TEXT PRIMARY KEY, document TEXT)')
        db.execute('INSERT INTO recovery_state VALUES (?,?)',('sandbox1',json.dumps({'failures':2})))
    with sqlite3.connect(root / 'platform.db') as db:
        db.execute('CREATE TABLE agents (agent_id TEXT PRIMARY KEY,config_path TEXT)')
        db.execute('INSERT INTO agents VALUES (?,?)',('agent',str(root / 'management/compiled/v1/agent')))
    return root


def contents(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def test_dry_run_is_default_and_does_not_write_source_or_destination(tmp_path):
    source = legacy(tmp_path); before = contents(source); destination = tmp_path / 'new'
    report = migrate(source,destination)
    assert report['jobs'] == 2 and report['jobs_needing_recovery'] == 1
    assert not destination.exists() and contents(source) == before
    assert 'retained-in-db-only' not in json.dumps(report)


def test_apply_requires_stop_confirmation(tmp_path):
    with pytest.raises(ValueError,match='services-stopped'):
        migrate(legacy(tmp_path),tmp_path / 'new',apply=True)


def test_apply_splits_jobs_preserves_blobs_and_remaps_paths(tmp_path):
    source = legacy(tmp_path); before = contents(source); destination = tmp_path / 'new'
    report = migrate(source,destination,apply=True,services_stopped=True)
    assert contents(source) == before
    assert (destination / 'migration-backup/management/catalog.db').exists()
    assert (destination / 'catalog_service/blobs/blob').read_bytes() == b'preserved resource'
    with sqlite3.connect(destination / 'catalog_service/catalog.db') as db:
        revision, document = db.execute('SELECT revision,document FROM catalog').fetchone(); document = json.loads(document)
        assert revision == 7 and 'jobs' not in document
        assert document['agents']['agent']['compiled'] == str(destination / 'catalog_service/compiled/v1/agent')
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='recovery_state'").fetchone()
    with sqlite3.connect(destination / 'operations/operations.db') as db:
        jobs = {row[0]:json.loads(row[1]) for row in db.execute('SELECT id,document FROM jobs')}
        assert jobs['job_old']['status'] == 'needs_recovery'
        assert jobs['job_old']['payload']['secret'] == 'retained-in-db-only'
        assert jobs['job_done']['status'] == 'succeeded'
        assert json.loads(db.execute('SELECT document FROM state WHERE key=?',('recovery:sandbox1',)).fetchone()[0])['failures'] == 2
    with sqlite3.connect(destination / 'sandbox_manager/platform.db') as db:
        registry_path = db.execute('SELECT config_path FROM agents').fetchone()[0]
        assert registry_path == str(destination / 'sandbox_manager/agents/legacy_compiled/v1/agent')
        assert (Path(registry_path) / 'config.json').exists()
    assert report['runtime_overrides']['WORKSPACE_ROOT'] == str(source / 'workspaces')
    assert not (destination / 'workspaces').exists()


def test_copy_workspace_is_explicit_and_source_remains(tmp_path):
    source = legacy(tmp_path); destination = tmp_path / 'new'
    report = migrate(source,destination,apply=True,services_stopped=True,copy_workspaces=True)
    assert (destination / 'workspaces/kept').read_text() == 'workspaces'
    assert (destination / 'file_service/state/kept').read_text() == 'state'
    assert (source / 'workspaces/kept').exists()
    assert report['runtime_overrides']['STATE_ROOT'] == str(destination / 'file_service/state')


def test_refuses_existing_or_overlapping_destination(tmp_path):
    source = legacy(tmp_path); destination = tmp_path / 'new'; destination.mkdir(); (destination / 'keep').write_text('keep')
    with pytest.raises(ValueError,match='never merged'): migrate(source,destination)
    with pytest.raises(ValueError,match='non-overlapping'): migrate(source,source / 'new')


def test_refuses_symlink_assets_without_partial_destination(tmp_path):
    source = legacy(tmp_path); (source / 'management/blobs/link').symlink_to(source / 'workspaces/kept')
    with pytest.raises(ValueError,match='Symlink'): migrate(source,tmp_path / 'new',apply=True,services_stopped=True)
    assert not (tmp_path / 'new').exists()


def test_load_test_ownership_moves_and_active_runs_do_not_replay(tmp_path):
    source = legacy(tmp_path)
    with sqlite3.connect(source / 'management/catalog.db') as db:
        db.execute('CREATE TABLE load_tests (id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL, document TEXT NOT NULL)')
        db.execute('CREATE TABLE load_test_users (username TEXT PRIMARY KEY, agent_id TEXT NOT NULL, run_id TEXT NOT NULL, state TEXT NOT NULL, document TEXT NOT NULL)')
        db.execute('INSERT INTO load_tests VALUES (?,?,?,?,?,?)',('run','request','fingerprint','running',1,json.dumps({'id':'run','status':'running'})))
        db.execute('INSERT INTO load_test_users VALUES (?,?,?,?,?)',('loadtest-user','agent','run','retained',json.dumps({'username':'loadtest-user'})))
    destination = tmp_path / 'new'
    migrate(source,destination,apply=True,services_stopped=True)
    with sqlite3.connect(destination / 'operations/operations.db') as db:
        assert db.execute('SELECT status FROM load_tests').fetchone()[0] == 'interrupted'
        assert db.execute('SELECT state FROM load_test_users').fetchone()[0] == 'retained'
    with sqlite3.connect(destination / 'catalog_service/catalog.db') as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='load_tests'").fetchone()
