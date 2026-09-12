import json

import pytest
from fastapi import HTTPException

from app.encrypted_transfer import encrypt, decrypt
from test_transfers import service, CONFIG, choices


def test_password_roundtrip_and_tampering():
    content = b'private-resource-key'
    envelope = json.loads(encrypt(content, 'long-test-passphrase'))
    assert 'private-resource-key' not in json.dumps(envelope)
    assert decrypt(envelope, 'long-test-passphrase') == content
    with pytest.raises(HTTPException):
        decrypt(envelope, 'wrong-test-passphrase')
    envelope['token'] = envelope['token'][:-10] + 'tampered!!'
    with pytest.raises(HTTPException):
        decrypt(envelope, 'long-test-passphrase')


def test_encrypted_import_preserves_credentials_but_preview_hides_them(service):
    preview = service.preview('opencode.json', json.dumps(CONFIG).encode())
    service.commit(preview['preview_id'], choices(preview))
    package = encrypt(service.export(include_secrets=True), 'long-test-passphrase')
    preview = service.preview('encrypted.json', package, 'long-test-passphrase')
    assert 'test-secret-key' not in json.dumps(preview)
    before = service.store.read()[1]['agents']
    service.commit(preview['preview_id'], choices(preview, '-new'))
    data = service.store.read()[1]
    assert data['models']['sample-demo-new']['api_key'] == 'test-secret-key'
    assert data['agents'] == before
