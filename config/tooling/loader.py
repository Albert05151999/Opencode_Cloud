from __future__ import annotations
import copy
import hashlib
import json
import os
import re
from pathlib import Path

MODULES = ('api_gateway', 'catalog_service', 'sandbox_manager', 'file_service', 'model_gateway', 'operations', 'observability', 'agent_runtime', 'admin_web', 'nginx')
class ConfigError(ValueError):
    pass

def read(path):
    return json.loads(Path(path).read_text())

def merge(base, override, prefix=''):
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key not in base:
            raise ConfigError(f'unknown field: {prefix}{key}')
        if isinstance(base[key], dict):
            if not isinstance(value, dict):
                raise ConfigError(f'expected object: {prefix}{key}')
            result[key] = merge(base[key], value, f'{prefix}{key}.')
        elif type(value) is not type(base[key]):
            raise ConfigError(f'invalid type: {prefix}{key}')
        else:
            result[key] = value
    return result

def load_config(root, module, profile='default', override=None, environ=None):
    root = Path(root)
    if module not in MODULES or not re.fullmatch(r'[a-zA-Z0-9_-]+', profile):
        raise ConfigError('unknown module or invalid profile')
    config = read(root / module / 'defaults.json')
    profiles = read(root / 'profiles' / profile / 'overrides.json')
    if set(profiles) - set(MODULES):
        raise ConfigError('unknown module in profile')
    config = merge(config, profiles.get(module, {}))
    if override:
        config = merge(config, read(override))
    env = os.environ if environ is None else environ
    prefix = f'CLOUD_{module.upper()}_'
    allowed = {prefix + key.upper() for key in config}
    unknown = {name for name in env if name.startswith(prefix)} - allowed
    if unknown: raise ConfigError(f'unknown environment fields: {sorted(unknown)}')
    for key in config:
        name = f'CLOUD_{module.upper()}_{key.upper()}'
        if name in env:
            if key in ('module_id', 'schema_version', 'services', 'settings'):
                raise ConfigError(f'environment override forbidden: {name}')
            value = env[name]
            if isinstance(config[key], int):
                try: value = int(value)
                except ValueError as exc: raise ConfigError(f'invalid integer: {name}') from exc
            config[key] = value
    if config['module_id'] != module or config['schema_version'] != 1:
        raise ConfigError('module/schema mismatch')
    if not 1 <= config['port'] <= 65535:
        raise ConfigError('port outside 1..65535')
    if not re.fullmatch(r'\$\{[A-Z][A-Z0-9_]*\}', config['service_token']):
        raise ConfigError('service_token must be an environment secret reference')
    for key in ('host', 'data_root', 'log_root'):
        if not config[key]: raise ConfigError(f'missing {key}')
    for value in config['services'].values():
        if not value.startswith(('http://', 'https://')): raise ConfigError('invalid service URL')
    def validate_secrets(value):
        for key, item in value.items():
            if isinstance(item, dict): validate_secrets(item)
            elif key.lower().endswith(('token', 'password', 'api_key')):
                if not isinstance(item, str) or not re.fullmatch(r'\$\{[A-Z][A-Z0-9_]*\}', item):
                    raise ConfigError(f'{key} must be an environment secret reference')
    validate_secrets(config)
    return config

def render(root, module, output, profile='default', override=None, environ=None):
    config = load_config(root, module, profile, override, environ)
    payload = json.dumps(config, indent=2, sort_keys=True) + '\n'
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'config.json').write_text(payload)
    manifest = {'module_id': module, 'schema_version': 1, 'profile': profile,
                'sources': [str(Path(root) / module / 'defaults.json'), str(Path(root) / 'profiles' / profile / 'overrides.json')],
                'sha256': hashlib.sha256(payload.encode()).hexdigest(), 'effective': config}
    if override: manifest['sources'].append(str(override))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return config
