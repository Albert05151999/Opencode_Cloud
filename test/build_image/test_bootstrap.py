import json
import shutil
from pathlib import Path

import pytest

from config.tooling.bootstrap import presets, initialize
from config.tooling.deployment_env import serialize

ROOT = Path(__file__).resolve().parents[2]


def test_empty_configuration_does_not_create_records():
    assert presets(ROOT / 'config', {}) == {'schema_version': 1, 'models': [], 'templates': []}
    assert not presets(ROOT / 'config', {'ADMIN_TOKEN': 'test'})['models']


def test_accounts_share_alias_and_agents_are_opt_in():
    config = {'MINIMAX_API_KEY': 'a', 'MINIMAX_API_KEY_2': 'b', 'ZAI_API_KEY': 'c'}
    result = presets(ROOT / 'config', config)
    assert [m['id'] for m in result['models']] == ['minimax', 'glm']
    assert len(result['models'][0]['deployments']) == 2
    assert all(d['enabled'] for d in result['models'][0]['deployments'])
    assert result['templates'] == []
    result = presets(ROOT / 'config', {**config, 'PRESET_AGENTS': 'code:glm,data:minimax'})
    assert [a['agent_id'] for a in result['templates']] == ['agent-code', 'agent-data']
    assert len(presets(ROOT / 'config', {'ZAI_API_KEY_2': 'a'})['models']) == 1


@pytest.mark.parametrize('values', [
    {'PRESET_AGENTS': 'code:glm'},
    {'ZAI_API_KEY': 'x', 'PRESET_AGENTS': 'code:glm,code:glm'},
    {'ZAI_API_KEY': 'x', 'BOOTSTRAP_BUNDLE': 'backup.json'},
])
def test_invalid_initialization_fails_before_writes(values):
    with pytest.raises(ValueError):
        presets(ROOT / 'config', values)


def test_initialization_waits_for_publish_and_repeated_install_preserves_changes(tmp_path):
    shutil.copytree(ROOT / 'config', tmp_path / 'config')
    (tmp_path / '.env').write_text(serialize({'ZAI_API_KEY': 'test', 'PRESET_AGENTS': 'code:glm'}))
    calls = []
    class Client:
        def __call__(self, path, payload=None, **kwargs):
            calls.append(path)
            return {'revision': 2, 'models': []}
        def publish(self, path):
            calls.append(path)
    initialize(tmp_path, Client())
    assert calls[-1] == '/cloud/admin/agents/agent-code/apply'
    assert calls.index('/cloud/admin/models/apply') < calls.index('/cloud/admin/agent-templates/example-code/restore')
    first = calls[:]
    initialize(tmp_path, Client())
    assert calls == first


def test_failed_publish_does_not_mark_initialization_complete(tmp_path):
    shutil.copytree(ROOT / 'config', tmp_path / 'config')
    (tmp_path / '.env').write_text('ZAI_API_KEY=test\n')
    class Client:
        def __call__(self, path, payload=None):
            return {'revision': 0, 'models': []}
        def publish(self, path):
            raise ValueError('upstream failed')
    with pytest.raises(ValueError, match='upstream failed'):
        initialize(tmp_path, Client())
    state = json.loads((tmp_path / 'data/bootstrap.json').read_text())
    assert state['completed'] == ['models.import']
