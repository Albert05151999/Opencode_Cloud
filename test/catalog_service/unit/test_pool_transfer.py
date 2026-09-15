import json
from catalog_service.src.management import ManagementStore
from catalog_service.src.transfers import Transfers
from catalog_service.src.encrypted_transfer import encrypt


def test_encrypted_multi_account_roundtrip_preserves_alias_and_keys(tmp_path):
    source = ManagementStore(tmp_path / 'source', tmp_path / 'templates')
    source.save_model('glm', {'id': 'glm', 'name': 'GLM', 'provider': 'openai-compatible',
        'upstream_model': 'upstream', 'base_url': 'https://example.com/v1', 'enabled': True,
        'deployments': [{'id': 'one', 'api_key': 'key-one'}, {'id': 'two', 'api_key': 'key-two'}]})
    exporter = Transfers(source)
    raw = exporter.export(True)
    encrypted = encrypt(raw, 'roundtrip-test-password')
    target = ManagementStore(tmp_path / 'target', tmp_path / 'templates')
    importer = Transfers(target)
    preview = importer.preview('config.json', encrypted, 'roundtrip-test-password')
    assert not any(i.get('warnings') for i in preview['items'])
    importer.commit(preview['preview_id'], [{'key': i['key'], 'target_id': i['id'], 'replace': False} for i in preview['items']])
    model = target.read()[1]['models']['glm']
    assert model['enabled']
    assert [a['api_key'] for a in model['deployments']] == ['key-one', 'key-two']
    assert len(target.read()[1]['models']) == 1
    redacted = exporter.export()
    assert b'key-one' not in redacted and b'key-two' not in redacted
    other = Transfers(ManagementStore(tmp_path / 'other', tmp_path / 'templates'))
    preview = other.preview('config.json', redacted)
    assert preview['items'][0]['warnings']
    other.commit(preview['preview_id'], [{'key': '0', 'target_id': 'glm', 'replace': False}])
    assert not other.store.read()[1]['models']['glm']['enabled']
