import json
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

from build_image import build
from config.tooling.deployment_env import initialize, private_environment
from config.tooling.seed import apply_seed, read_env_file


def test_private_bundle_contains_credentials_but_images_do_not(tmp_path, monkeypatch):
    env_file = tmp_path / 'input.env'
    env_file.write_text('MINIMAX_API_KEY=private-minimax\nZAI_API_KEY=private-glm\n'
                        'SERVER_PASSWORD=local-only\nCODING_FAST_API_KEY=retired\n'
                        'DEPLOY_ROOT=/old/host\nDOCKER_BRIDGE_IP=172.31.0.1\n')
    def fake_run(*args):
        if args[1] == 'save':
            Path(args[3]).write_bytes(b'image')
    monkeypatch.setattr(build, 'run', fake_run)
    artifacts = tmp_path / 'artifacts'
    release = build.bundle(artifacts=artifacts, env_file=env_file)
    values = read_env_file(release / '.env')
    assert values['MINIMAX_API_KEY'] == 'private-minimax'
    assert values['ZAI_API_KEY'] == 'private-glm'
    assert not values['DEPLOY_ROOT'] and not values['DOCKER_BRIDGE_IP']
    assert 'SERVER_PASSWORD' not in values and 'CODING_FAST_API_KEY' not in values
    assert json.loads((release / 'manifest.json').read_text())['private_environment']
    for path in (artifacts / 'contexts').rglob('*'):
        if path.is_file():
            assert b'private-minimax' not in path.read_bytes()
    with tarfile.open(artifacts / 'releases' / f'release-{build.VERSION}.tar.gz') as archive:
        assert archive.getmember(f'release-{build.VERSION}/.env').mode == 0o600
        assert b'private-minimax' in archive.extractfile(f'release-{build.VERSION}/.env').read()
    # Initialization must not invalidate the immutable release inventory.
    initialize(release / '.env', release)
    from build_image.tools.verify_release import verify
    assert verify(release)['images'] == len(build.MODULES)
    # Root .env is now selected automatically; explicit empty env produces an empty platform.
    empty = tmp_path / 'empty.env'
    empty.write_text('')
    build.bundle(prepare_only=True, artifacts=artifacts, env_file=empty)
    assert not read_env_file(release / '.env')['MINIMAX_API_KEY']


def test_initialize_partial_env_preserves_keys_and_tokens_and_is_repeatable(tmp_path):
    path = tmp_path / '.env'
    path.write_text("MINIMAX_API_KEY='literal$KEY#value'\nADMIN_TOKEN=existing\n"
                    'SERVICE_TOKEN=\nMODEL_GATEWAY_TOKEN=\nDEPLOY_ROOT=\n')
    initialize(path, tmp_path)
    first = read_env_file(path)
    assert first['MINIMAX_API_KEY'] == 'literal$KEY#value'
    assert first['ADMIN_TOKEN'] == 'existing'
    assert len(first['SERVICE_TOKEN']) == len(first['MODEL_GATEWAY_TOKEN']) == 64
    assert first['SERVICE_TOKEN'] != first['MODEL_GATEWAY_TOKEN']
    assert first['DEPLOY_ROOT'] == str(tmp_path.resolve())
    initialize(path, tmp_path)
    assert read_env_file(path) == first


def test_invalid_env_is_rejected_before_existing_release_is_replaced(tmp_path):
    release = tmp_path / 'artifacts/releases' / build.VERSION
    release.mkdir(parents=True)
    (release / 'preserve').write_text('existing release')
    env_file = tmp_path / 'bad.env'
    env_file.write_text('API_PORT=65536\n')
    with pytest.raises(ValueError, match='API_PORT'):
        build.bundle(prepare_only=True, artifacts=tmp_path / 'artifacts', env_file=env_file)
    assert (release / 'preserve').exists()


def test_two_model_seed_resolves_only_two_upstream_credentials(tmp_path):
    env_file = tmp_path / '.env'
    env_file.write_text('MINIMAX_API_KEY=key-a\nZAI_API_KEY=key-b\nADMIN_TOKEN=admin\n')
    env_file.write_text(private_environment(env_file))
    requests = []
    apply_seed(build.ROOT / 'config', 'models.minimax-glm.json', apply=True,
               catalog_url='http://127.0.0.1:18080', revision=0, env_file=env_file,
               environ={}, request=lambda path, payload: requests.append((path, payload)))
    models = requests[0][1]['models']
    assert [m['id'] for m in models] == ['minimax', 'glm']
    assert [m['deployments'][0]['api_key'] for m in models] == ['key-a', 'key-b']
    assert [m['upstream_model'] for m in models] == ['MiniMax-M3', 'glm-5.3']


def test_release_env_initializer_works_without_source_checkout(tmp_path):
    release = tmp_path / 'release'
    build.include_seed_tools(build.ROOT, release)
    import os
    env = dict(os.environ, PYTHONPATH=str(release / 'tooling'))
    result = subprocess.run([sys.executable, '-m', 'config.tooling.deployment_env',
                             '--env-file', str(release / '.env'), '--deploy-root', str(release)],
                            cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert len(read_env_file(release / '.env')['ADMIN_TOKEN']) == 64


def test_selected_pool_ships_alias_mapping_and_only_referenced_credentials(tmp_path):
    env_file = tmp_path / 'private.env'
    env_file.write_text('MINIMAX_API_KEY=key-a\nZAI_API_KEY=key-b\nMINIMAX_API_KEY_2=key-c\nSERVER_PASSWORD=never-package\n')
    release = build.bundle(prepare_only=True, artifacts=tmp_path / 'artifacts', env_file=env_file)
    values = read_env_file(release / '.env')
    assert values['MINIMAX_API_KEY_2'] == 'key-c' and 'SERVER_PASSWORD' not in values
    seed = json.loads((release / 'config/catalog_service/seeds/models.minimax-glm.json').read_text())
    assert [m['id'] for m in seed['models']] == ['minimax', 'glm']
    assert seed['models'][0]['deployments'][1]['api_key'] == '${MINIMAX_API_KEY_2}'
    from config.tooling.seed import resolve
    resolved = resolve(seed, values)
    assert resolved['models'][1]['deployments'][1]['api_key'] == ''
    seed['models'][1]['deployments'][1]['enabled'] = True
    with pytest.raises(ValueError, match='ZAI_API_KEY_2'): resolve(seed, values)
