import json
from pathlib import Path
import pytest
from config.tooling.loader import ConfigError, load_config, render
ROOT = Path(__file__).resolve().parents[3] / 'config'

def test_precedence_and_secret_reference(tmp_path):
    override = tmp_path / 'override.json'
    override.write_text(json.dumps({'port': 1234}))
    value = render(ROOT, 'api_gateway', tmp_path / 'out', override=override,
                   environ={'CLOUD_API_GATEWAY_PORT': '2345', 'SERVICE_TOKEN': 'must-never-appear'})
    assert value['port'] == 2345
    assert 'must-never-appear' not in (tmp_path / 'out/manifest.json').read_text()
    assert value['service_token'] == '${SERVICE_TOKEN}'

@pytest.mark.parametrize('override', [{'typo': 1}, {'port': 0}, {'port': '123'}, {'service_token': 'literal-secret'}, {'settings': {'admin_token': 'secret'}}])
def test_invalid_config_rejected(tmp_path, override):
    path = tmp_path / 'override.json'; path.write_text(json.dumps(override))
    with pytest.raises(ConfigError): load_config(ROOT, 'api_gateway', override=path, environ={})

def test_unknown_module_and_profile_traversal():
    for module, profile in [('api-gateway', 'default'), ('api_gateway', '../default')]:
        with pytest.raises(ConfigError): load_config(ROOT, module, profile)


def test_environment_typo_rejected():
    with pytest.raises(ConfigError):
        load_config(ROOT, 'api_gateway', environ={'CLOUD_API_GATEWAY_POTR': '8080'})
