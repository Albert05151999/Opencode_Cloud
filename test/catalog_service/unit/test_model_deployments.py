import copy
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from catalog_service.src.admin_dto import ModelDefinition
from catalog_service.src.compiler import Compiler
from catalog_service.src.management import ManagementStore, redact, validate_model
from model_gateway.src.models import compile_model


def pool():
    return {'id': 'coding-fast', 'provider': 'openai-compatible', 'upstream_model': 'MiniMax-M3',
            'base_url': 'https://example.test/v1', 'deployments': [
                {'id': 'account-a', 'api_key': 'key-a', 'rpm': 60, 'weight': 1},
                {'id': 'account-b', 'api_key': 'key-b', 'rpm': 120, 'weight': 2},
                {'id': 'disabled', 'api_key': '', 'enabled': False},
            ]}


def test_publish_preview_and_probe_share_deployments():
    model = ModelDefinition.model_validate(pool()).model_dump()
    validate_model(model)
    published = Compiler(None, None).gateway_configuration({model['id']: model}, {})
    tested = compile_model(model)
    assert published['model_list'] == tested['model_list']
    assert [e['model_name'] for e in published['model_list']] == ['coding-fast'] * 2
    assert [e['litellm_params']['api_key'] for e in published['model_list']] == ['key-a', 'key-b']
    assert [e['model_info']['id'] for e in published['model_list']] == ['coding-fast:account-a', 'coding-fast:account-b']
    assert published['router_settings']['routing_strategy'] == 'simple-shuffle'
    assert published['router_settings']['enable_pre_call_checks']
    assert 'key-a' not in json.dumps(redact(published))


def test_edit_reorder_remove_and_migrate_preserve_credentials_by_identity(tmp_path):
    store = ManagementStore(tmp_path / 'catalog', tmp_path / 'empty-agents')
    model = pool()
    store.save_model('coding-fast', model)
    edited = redact(store.read()[1]['models']['coding-fast'])
    edited['deployments'] = edited['deployments'][1::-1]
    edited['name'] = 'Changed name'
    store.save_model('coding-fast', edited)
    saved = store.read()[1]['models']['coding-fast']
    assert [r['api_key'] for r in saved['deployments']] == ['key-b', 'key-a']
    edited['deployments'][0]['id'] = 'new-account'
    with pytest.raises(HTTPException):
        store.save_model('coding-fast', edited)
    assert store.read()[1]['models']['coding-fast'] == saved
    single = {k: v for k, v in pool().items() if k != 'deployments'}
    single['api_key'] = 'original-key'
    store.save_model('coding-fast', single)
    migrated = {**single, 'api_key': '', 'deployments': [{'id': 'primary', 'api_key': '••••'}]}
    store.save_model('coding-fast', migrated)
    assert store.read()[1]['models']['coding-fast']['deployments'][0]['api_key'] == 'original-key'


@pytest.mark.parametrize('change', [
    {'rpm': 0}, {'tpm': 1.5}, {'weight': float('nan')},
    {'base_url': 'https://user:password@example.test/v1'}, {'id': 'account-b'},
])
def test_invalid_deployments_are_rejected(change):
    value = pool()
    value['deployments'][0].update(change)
    with pytest.raises(HTTPException): validate_model(value)


def test_probe_requires_every_enabled_key_and_rejects_mixed_modes():
    value = pool()
    value['deployments'][0]['api_key'] = '${MISSING}'
    with pytest.raises(HTTPException, match='real API key'): compile_model(value)
    value['api_key'] = 'ambiguous'
    with pytest.raises(HTTPException): validate_model(value)
