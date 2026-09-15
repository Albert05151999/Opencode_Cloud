"""Private deployment dotenv: parsed as data, never sourced by a shell."""
from pathlib import Path
import argparse
import secrets

from config.tooling.seed import read_env_file

TOKENS = ('SERVICE_TOKEN', 'ADMIN_TOKEN', 'MODEL_GATEWAY_TOKEN')
DEFAULTS = {
    **dict.fromkeys(TOKENS, ''),
    'DEPLOY_ROOT': '',
    'COMPOSE_PROJECT_NAME': 'opencode_cloud',
    'API_PORT': '18080',
    'HTTPS_PORT': '443',
    'DOCKER_BRIDGE_IP': '',
    'MINIMAX_API_KEY': '',
    'MINIMAX_BASE_URL': 'https://api.minimaxi.com/v1',
    'MINIMAX_MODEL': 'MiniMax-M3',
    'ZAI_API_KEY': '',
    'ZAI_BASE_URL': 'https://api.z.ai/api/coding/paas/v4',
    'ZAI_MODEL': 'glm-5.3',
    'MINIMAX_API_KEY_2': '',
    'ZAI_API_KEY_2': '',
    'PRESET_AGENTS': '',
    'BOOTSTRAP_BUNDLE': '',
    'BOOTSTRAP_PASSWORD': '',
}


def serialize(values):
    lines = []
    for key, value in values.items():
        # Single quotes prevent Compose interpolation, and are also understood
        # literally by seed.read_env_file. Do not invent an escaping dialect.
        if any(char in value for char in "'\r\n\x00"):
            raise ValueError(f'Unsupported dotenv characters in {key}')
        lines.append(f"{key}='{value}'" if value else f'{key}=')
    return '\n'.join(lines) + '\n'


def private_environment(path, extra_names=()):
    """Select current server/model fields; exclude local SSH and retired aliases."""
    source = read_env_file(path)
    values = {key: source.get(key, default) for key, default in DEFAULTS.items()}
    values.update({key: source.get(key, '') for key in extra_names if key not in values})
    # A release may be installed on a different host and in a different directory.
    values['DEPLOY_ROOT'] = values['DOCKER_BRIDGE_IP'] = ''
    for key in ('API_PORT', 'HTTPS_PORT'):
        if not values[key].isdigit() or not 1 <= int(values[key]) <= 65535:
            raise ValueError(f'{key} must be a port between 1 and 65535')
    return serialize(values)


def initialize(path, deploy_root):
    path = Path(path)
    values = read_env_file(path) if path.exists() else {}
    for key in TOKENS:
        if not values.get(key):
            values[key] = secrets.token_hex(32)
    if not values.get('DEPLOY_ROOT'):
        values['DEPLOY_ROOT'] = str(Path(deploy_root).resolve())
    if not values.get('COMPOSE_PROJECT_NAME'):
        values['COMPOSE_PROJECT_NAME'] = DEFAULTS['COMPOSE_PROJECT_NAME']
    payload = serialize(values)
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        path.chmod(0o600)
        stream.write(payload)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--deploy-root', type=Path, required=True)
    args = parser.parse_args()
    try:
        initialize(args.env_file, args.deploy_root)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
