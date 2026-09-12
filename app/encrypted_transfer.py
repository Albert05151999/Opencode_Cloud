"""Versioned password envelopes using cryptography's authenticated Fernet format."""
import base64
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app.management import fail

FORMAT = 'opencode-cloud-encrypted'


def cipher(password, salt):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        fail('Use a passphrase between 12 and 1024 characters')
    key = Scrypt(salt=salt, length=32, n=32768, r=8, p=1).derive(password.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(content, password):
    salt = os.urandom(16)
    token = cipher(password, salt).encrypt(content).decode()
    return json.dumps({'format': FORMAT, 'format_version': 1,
                      'salt': base64.b64encode(salt).decode(), 'token': token}).encode()


def decrypt(envelope, password):
    try:
        if envelope.get('format') != FORMAT or envelope.get('format_version') != 1:
            fail('Unsupported encrypted transfer format')
        salt = base64.b64decode(envelope['salt'], validate=True)
        if len(salt) != 16:
            fail('Invalid encrypted transfer salt')
        return cipher(password, salt).decrypt(envelope['token'].encode())
    except (ValueError, KeyError, AttributeError, InvalidToken):
        fail('Incorrect passphrase or damaged encrypted package')
