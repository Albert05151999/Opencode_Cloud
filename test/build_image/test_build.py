import json
from pathlib import Path
import pytest
from build_image.build import ROOT, MODULES, bundle, compose_document, nginx_config, prepare_module
from config.tooling.loader import ConfigError, load_config

def nginx_settings(**overrides):
    return {'domain': 'cloud.example.com', 'certificate': '/etc/nginx/tls/fullchain.pem', 'private_key': '/etc/nginx/tls/privkey.pem', 'log_max_bytes': 10485760, 'log_backup_count': 5, **overrides}

def test_isolated_context(tmp_path):
    output, tag, cfg = prepare_module('api_gateway', artifacts=tmp_path)
    assert (output / 'api_gateway').is_dir()
    assert (output / 'shared_libs').is_dir()
    assert not (output / 'app').exists()
    assert not (output / 'admin_web').exists()
    assert not (output / 'config').exists()
    assert 'COPY . ' not in (output / 'Dockerfile').read_text()

def test_ip_bundle_excludes_frontend_and_nginx(tmp_path):
    release = bundle(prepare_only=True, artifacts=tmp_path)
    doc = json.loads((release / 'compose.json').read_text())
    assert 'admin_web' not in doc['services'] and 'nginx' not in doc['services']
    assert 'agent_runtime' not in doc['services']
    assert 'ports' in doc['services']['api_gateway']
    assert not (release / 'SHA256SUMS').exists()  # cannot install an unbuilt release
    assert (tmp_path / 'scripts/server/install.sh').exists()
    assert all('docker.sock' not in str(s) for m,s in doc['services'].items() if m!='sandbox_manager')

def test_domain_validation_and_streaming():
    with pytest.raises(ConfigError): nginx_config({'settings': {'domain': ''}})
    result = nginx_config({'settings': nginx_settings()})
    assert 'proxy_buffering off' in result and 'proxy_request_buffering off' in result
    assert 'listen 443 ssl' in result


@pytest.mark.parametrize('key,value', [('log_max_bytes',1023),('log_max_bytes',True),('log_backup_count',0),('log_backup_count',21),('log_backup_count',False)])
def test_domain_rejects_invalid_log_rotation_before_build(key,value):
    with pytest.raises(ConfigError,match=key):
        nginx_config({'settings':nginx_settings(**{key:value})})


def test_domain_compose_maps_configured_log_rotation():
    from build_image.build import preflight_bundle
    configs=preflight_bundle()
    configs['nginx']=load_config(ROOT/'config','nginx')
    configs['nginx']['settings'].update(log_max_bytes=2048,log_backup_count=2)
    tags={module:module for module in (*MODULES,'nginx')}
    nginx=compose_document(tags,configs,'domain')['services']['nginx']
    assert nginx['environment']['NGINX_LOG_MAX_BYTES']=='2048'
    assert nginx['environment']['NGINX_LOG_BACKUP_COUNT']=='2'


def test_domain_nginx_logs_safe_json_and_forwards_validated_trace_context():
    result = nginx_config({'settings': nginx_settings()})
    assert 'log_format cloud_json escape=json' in result
    assert 'access_log /log/nginx/__NGINX_INSTANCE__/events.jsonl cloud_json' in result
    assert 'proxy_set_header traceparent "00-$trace_id-$nginx_span_id-01"' in result
    assert '"~^(?<generated_span_id>[0-9a-f]{16})"' in result
    assert '"~^00-(?<validated_incoming_trace_id>' in result
    assert '(?!0{32})[0-9a-f]{32}' in result
    assert '"path":"$uri"' in result
    for secret_source in ('$request_uri', '$args', '$http_authorization', '$http_cookie'):
        assert secret_source not in result


def test_nginx_context_contains_bounded_log_entrypoint(tmp_path):
    output, _, _ = prepare_module('nginx', artifacts=tmp_path)
    script = (output / 'nginx-entrypoint.sh').read_text()
    dockerfile = (output / 'Dockerfile').read_text()
    assert 'NGINX_LOG_MAX_BYTES' in script and 'NGINX_LOG_BACKUP_COUNT' in script
    assert 'events.jsonl' in script and '-s reopen' in script
    assert 'chmod 0711 "$LOG_BASE"' in script
    assert 'sleep 1 & wait $!' in script
    assert 'chown nginx:nginx "$target"' in script and 'chmod 0644 "$target"' in script
    assert script.index('create_log_file\n  nginx') < script.index('-s reopen')
    assert 'trap graceful_stop QUIT' in script and 'kill -QUIT "$NGINX_PID"' in script
    assert 'ENTRYPOINT ["/usr/local/bin/cloud-nginx-entrypoint"]' in dockerfile


def test_host_docker_mount_and_network_contract(tmp_path):
    release = bundle(prepare_only=True, artifacts=tmp_path)
    services = json.loads((release / 'compose.json').read_text())['services']
    manager = services['sandbox_manager']
    assert manager['network_mode'] == 'host'
    assert 'ports' not in manager
    assert manager['environment']['FILE_SERVICE_URL'] == 'http://127.0.0.1:8103'
    assert services['file_service']['environment']['WORKSPACE_ROOT'] == manager['environment']['WORKSPACE_ROOT']
    assert any(volume.split(':')[0].startswith('${DEPLOY_ROOT') for volume in manager['volumes'])
    assert services['model_gateway']['ports'] == ['${DOCKER_BRIDGE_IP:?run install.sh to detect Docker bridge}:8104:8104', '127.0.0.1:8104:8104']
    assert manager['environment']['SERVICE_HOST'].startswith('${DOCKER_BRIDGE_IP:')


def test_offline_archive_includes_all_images_and_verified_inventory(tmp_path, monkeypatch):
    import hashlib
    import tarfile
    import build_image.build as build
    calls = []
    def fake_run(*args):
        calls.append(args)
        if args[1] == 'save':
            Path(args[3]).write_bytes(('image:' + args[4]).encode())
    monkeypatch.setattr(build, 'run', fake_run)
    release = build.bundle(artifacts=tmp_path)
    assert len([c for c in calls if c[1] == 'build']) == len(MODULES)
    assert len(list((release / 'images').glob('*.tar'))) == len(MODULES)
    from build_image.tools.verify_release import verify
    assert verify(release)['images'] == len(MODULES)
    for line in (release / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        assert hashlib.sha256((release / name).read_bytes()).hexdigest() == digest
    with tarfile.open(tmp_path / f'releases/release-{build.VERSION}.tar.gz') as archive:
        assert not any('/admin_web/' in name or '/app/' in name for name in archive.getnames())


def test_script_collection_keeps_admin_independent(tmp_path):
    from build_image.tools.export_scripts import export_scripts
    for relative in ('build_image/bundle/install.sh', 'build_image/docker/install-docker.sh', 'admin_web/scripts/start.sh'):
        path = tmp_path / relative; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\nexit 0\n')
    export_scripts(tmp_path)
    assert (tmp_path / 'artifacts/scripts/admin_web/start.sh').exists()
    assert (tmp_path / 'artifacts/scripts/server/install-docker.sh').exists()
    assert not (tmp_path / 'artifacts/scripts/server/start.sh').exists()


def test_runtime_rendered_config_is_consumed_by_entrypoint(tmp_path):
    output,_,config=prepare_module('agent_runtime',artifacts=tmp_path)
    dockerfile=(output/'Dockerfile').read_text()
    assert 'COPY config.json /config/config.json' in dockerfile
    assert 'runtime-config.py' in dockerfile
    assert (output/'agent_runtime/image/entrypoint.sh').exists()
    assert (output/'agent_runtime/image/smoke/image-smoke.sh').exists()
    import runpy
    from unittest.mock import patch
    captured={}
    def execv(path,args): captured.update(path=path,args=args)
    with patch.dict('os.environ',{'MODULE_CONFIG':str(output/'config.json')},clear=True), patch('os.execv',side_effect=execv):
        runpy.run_path(str(output/'runtime-config.py'))
        import os
        assert os.environ['OPENCODE_PORT']==str(config['port'])
    assert captured['path']=='/opt/venv/bin/python'
    assert captured['args'][-1]=='/usr/local/bin/runtime-entrypoint'
