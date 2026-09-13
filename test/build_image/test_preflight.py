import json
from pathlib import Path
import shutil
import pytest
import build_image.build as build
from config.tooling.loader import ConfigError

@pytest.mark.parametrize('overrides,match',[
    ({'agent_runtime':{'port':4097}},'agent_runtime port'),
    ({'catalog_service':{'settings':{'model_gateway_public_url':'http://wrong-host:8104/v1'}}},'must match sandbox_manager'),
    ({'model_gateway':{'port':9104}},'Runtime model gateway URL port'),
    ({'file_service':{'port':9103}},'services.file_service port'),
    ({'catalog_service':{'settings':{'model_gateway_public_url':'http://host.docker.internal:8104/wrong'}},'sandbox_manager':{'settings':{'controller_config':{'model_gateway':{'base_url':'http://host.docker.internal:8104/wrong'}}}}},'HTTP\\(S\\) /v1'),
])
def test_invalid_contract_fails_before_build_or_release_changes(tmp_path,monkeypatch,overrides,match):
    root=tmp_path/'source';shutil.copytree(build.ROOT/'config',root/'config')
    shutil.copy2(build.ROOT/'VERSION',root/'VERSION')
    (root/'config/profiles/production/overrides.json').write_text(json.dumps(overrides))
    release=tmp_path/'artifacts/releases'/build.VERSION;release.mkdir(parents=True);sentinel=release/'preserve';sentinel.write_text('existing')
    monkeypatch.setattr(build,'build_module',lambda *args,**kwargs:pytest.fail('preflight must run before any image build'))
    with pytest.raises(ConfigError,match=match):build.bundle(root=root,artifacts=tmp_path/'artifacts')
    assert sentinel.read_text()=='existing'


def test_production_and_acceptance_contracts_match():
    assert build.preflight_bundle()['agent_runtime']['port']==4096
    assert build.preflight_bundle(profile='acceptance')['catalog_service']['settings']['sandbox']['default_cpu']==1


def test_acceptance_domain_preserves_server_profile_and_checks_tls(tmp_path):
    ip=build.preflight_bundle(profile='acceptance')
    domain=build.preflight_bundle(profile='acceptance_domain',mode='domain')
    assert ip==domain
    release=build.bundle(profile='acceptance_domain',mode='domain',prepare_only=True,artifacts=tmp_path)
    document=json.loads((release/'compose.json').read_text())
    assert 'ports' not in document['services']['api_gateway']
    nginx=document['services']['nginx']
    assert nginx['ports']==['${HTTPS_PORT:-443}:443']
    assert './config/nginx/tls:/etc/nginx/tls:ro' in nginx['volumes']
    assert './log:/log' in nginx['volumes']
    assert nginx['environment']=={'LOG_ROOT':'/log','NGINX_LOG_MAX_BYTES':'2048','NGINX_LOG_BACKUP_COUNT':'2'}
    defaults=build.load_config(build.ROOT/'config','nginx','production')['settings']
    assert (defaults['log_max_bytes'],defaults['log_backup_count'])==(10485760,5)
    assert nginx['healthcheck']['test'][-1]=='https://127.0.0.1/cloud/health'
    text=(release/'config/nginx/nginx.conf').read_text()
    assert 'cloud-acceptance.invalid' in text and 'proxy_buffering off' in text
    assert 'ssl_certificate /etc/nginx/tls/fullchain.pem' in text
    assert 'access_log /log/nginx/__NGINX_INSTANCE__/events.jsonl cloud_json' in text
