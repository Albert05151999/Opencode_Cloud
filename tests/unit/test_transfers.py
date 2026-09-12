import copy
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.management import ManagementStore
from app.transfers import Transfers, FORMAT

ROOT = Path(__file__).resolve().parents[2]
CONFIG = {'provider': {'sample': {'npm': '@ai-sdk/openai-compatible',
          'options': {'baseURL': 'https://example.org/v1', 'apiKey': 'test-secret-key'},
          'models': {'demo': {'name': 'Demo'}}}},
          'mcp': {'docs': {'type': 'remote', 'url': 'https://example.org/mcp', 'headers': {'Authorization': 'private-header'}}}}
SKILL = b'---\nname: example-skill\ndescription: Example skill\n---\nUse the included script.'


@pytest.fixture
def service(tmp_path):
    return Transfers(ManagementStore(tmp_path / 'management', ROOT / 'agents'))


def choices(preview, suffix=''):
    return [{'key': e['key'], 'target_id': e['id'] + suffix, 'replace': False} for e in preview['items'] if not e.get('error')]


def test_native_import_is_staged_and_never_assigns_agents(service):
    before = service.store.read()
    preview = service.preview('opencode.json', json.dumps(CONFIG).encode())
    assert service.store.read() == before
    assert 'test-secret-key' not in json.dumps(preview) and 'private-header' not in json.dumps(preview)
    result = service.commit(preview['preview_id'], choices(preview))
    assert result['assigned_agents'] == [] and result['published'] is False
    _, data = service.store.read()
    assert data['agents'] == before[1]['agents']
    assert data['resources']['docs']['owner'] is None
    assert data['resources']['docs']['versions'] == []
    assert data['models']['sample-demo']['api_key'] == 'test-secret-key'
    assert service.commit(preview['preview_id'], choices(preview)) == result


def test_skill_roundtrip_preserves_content(service):
    preview = service.preview('SKILL.md', SKILL)
    service.commit(preview['preview_id'], choices(preview))
    exported = service.export()
    preview = service.preview('resources.json', exported)
    service.commit(preview['preview_id'], choices(preview, '-copy'))
    _, data = service.store.read()
    assert data['resources']['example-skill-copy']['draft']['files'] == data['resources']['example-skill']['draft']['files']
    digest = data['resources']['example-skill']['draft']['files']['SKILL.md']
    assert service.store.file(digest) == SKILL


def test_catalog_revision_change_blocks_commit(service):
    preview = service.preview('config.json', json.dumps(CONFIG).encode())
    with service.store.edit() as data:
        data['changed'] = True
    with pytest.raises(HTTPException):
        service.commit(preview['preview_id'], choices(preview))
    assert 'sample-demo' not in service.store.read()[1]['models']


def test_duplicate_targets_roll_back_entire_import(service):
    preview = service.preview('config.json', json.dumps(CONFIG).encode())
    selections = choices(preview)
    selections.append(selections[-1])
    with pytest.raises(HTTPException):
        service.commit(preview['preview_id'], selections)
    assert 'docs' not in service.store.read()[1]['resources']
    assert 'sample-demo' not in service.store.read()[1]['models']


def test_missing_credential_import_stays_disabled(service):
    value = copy.deepcopy(CONFIG)
    del value['provider']['sample']['options']['apiKey']
    preview = service.preview('config.json', json.dumps(value).encode())
    service.commit(preview['preview_id'], choices(preview))
    assert service.store.read()[1]['models']['sample-demo']['enabled'] is False


def test_unresolved_references_are_visible_errors(service):
    value = copy.deepcopy(CONFIG)
    value['provider']['sample']['options']['apiKey'] = '{env:UNKNOWN}'
    preview = service.preview('config.json', json.dumps(value).encode())
    model = next(e for e in preview['items'] if e['kind'] == 'model')
    assert 'Unresolved' in model['error']


def test_exported_mcp_missing_secrets_is_disabled_on_new_destination(service):
    preview = service.preview('config.json', json.dumps(CONFIG).encode())
    service.commit(preview['preview_id'], choices(preview))
    content = service.export()
    assert b'test-secret-key' not in content and b'private-header' not in content
    preview = service.preview('resources.json', content)
    service.commit(preview['preview_id'], choices(preview, '-copy'))
    copied = service.store.read()[1]['resources']['docs-copy']['draft']['data']
    assert copied['enabled'] is False and copied['headers']['Authorization'] == ''


def test_future_format_and_empty_selection_rejected(service):
    with pytest.raises(HTTPException):
        service.preview('resources.json', json.dumps({'format': FORMAT, 'format_version': 99}).encode())
    preview = service.preview('config.json', b'{}')
    with pytest.raises(HTTPException):
        service.commit(preview['preview_id'], [])
