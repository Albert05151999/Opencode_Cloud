"""Real offline install/upgrade and imported-model validation in an owned test stack."""
import asyncio
import configparser
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from local_web.importer import Importer


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    import httpx
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--keep-running', action='store_true', help='Keep only this owned test stack for Windows companion verification')
    parser.add_argument('--from-version', default='0.2.2', choices=['0.1.0', '0.2.0', '0.2.2'])
    args = parser.parse_args()
    version = (ROOT / 'VERSION').read_text().strip()
    source = ROOT / ('artifacts/release/network-r1/cloud-agent-release-0.1.0-network-r1' if args.from_version == '0.1.0' else f'artifacts/release/web-v{args.from_version}/cloud-agent-release-{args.from_version}')
    bundle = ROOT / f'artifacts/release/web-v{version}/cloud-agent-release-{version}'
    root = Path(tempfile.mkdtemp(prefix='cloud-web-upgrade-', dir='/srv'))
    root.chmod(0o755)
    # This isolated test shares WSL with an existing gateway; retain the explicit
    # coexistence profile instead of altering host swap or other running services.
    (root / '.preflight-profile').write_text('coexistence-trial\n')
    instance = 'webupgrade-' + secrets.token_hex(5)
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(source / 'config/config.cfg')
    cfg['platform'].update(instance_id=instance, host='127.0.0.1', port='18082', data_root=str(root / 'data'))
    cfg['storage'].update(workspace_root=str(root / 'workspaces'), state_root=str(root / 'state'))
    cfg['metrics'].update(prometheus_port='19092', grafana_port='13002')
    cfg['model_gateway'].update(base_url='http://127.0.0.1:4002/v1', health_url='http://127.0.0.1:4002/health/liveliness')
    with (root / 'config.cfg').open('w') as f:
        cfg.write(f)
    report = {'root': str(root), 'instance': instance, 'from_version': args.from_version, 'to_version': version, 'result': 'running', 'checks': {}}
    deploy = module('upgrade_deploy', bundle / 'deploy/manage.py')
    client = httpx.Client(base_url='http://127.0.0.1:18082', timeout=180, trust_env=False)
    def api(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:400]}')
        return response.json()
    def wait_job(jid):
        for _ in range(240):
            item = api('GET', '/cloud/admin/jobs/' + jid)
            if item['status'] in {'succeeded', 'failed'}:
                if item['status'] != 'succeeded':
                    raise RuntimeError(item.get('error', 'job_failed'))
                return item
            time.sleep(1)
        raise RuntimeError('Job wait timed out')
    try:
        subprocess.run(['bash', str(source / 'deploy/install.sh'), '--root', str(root),
                        '--env-file', str(ROOT / 'deploy/.env')], check=True)
        if (root / 'data/admin-token').is_file():
            client.headers['Authorization'] = 'Bearer ' + (root / 'data/admin-token').read_text().strip()
        old = api('POST', '/session', json={'_cloud': {'agent_id': 'agent-code', 'username': 'migration'}})
        sid = old['id']
        report['checks']['legacy_install_and_session'] = True
        old_env = hashlib.sha256((root / '.env').read_bytes()).hexdigest()
        deploy.stop(root)
        subprocess.run(['bash', str(bundle / 'deploy/install.sh'), '--root', str(root),
                        '--env-file', str(ROOT / 'deploy/.env')], check=True)
        client.headers.pop('Authorization', None)
        assert client.get('/cloud/admin/catalog').status_code == 401
        client.headers['Authorization'] = 'Bearer ' + (root / 'data/admin-token').read_text().strip()
        assert api('GET', '/cloud/capabilities')['version'] == version
        assert api('GET', '/session/' + sid)['id'] == sid
        assert hashlib.sha256((root / '.env').read_bytes()).hexdigest() == old_env
        assert (root / '.instance-id').read_text().strip() == instance
        report['checks']['upgrade_preserves_session_identity_and_env'] = True
        # Create a local source that references a process environment key. No key is
        # written to the source file, returned in preview, or printed in this report.
        gateway = json.loads(subprocess.check_output(['docker', 'inspect', instance + '-model-gateway-1']))[0]
        environment = dict(e.split('=', 1) for e in gateway['Config']['Env'] if '=' in e)
        os.environ['WEB_VERIFY_MODEL_KEY'] = environment['CODING_FAST_API_KEY']
        upstream = environment['CODING_FAST_MODEL'].removeprefix('openai/')
        file = root / 'opencode.jsonc'
        file.write_text(json.dumps({'provider': {'imported': {'npm': '@ai-sdk/openai-compatible',
            'options': {'baseURL': environment['CODING_FAST_1_API_BASE'], 'apiKey': '{env:WEB_VERIFY_MODEL_KEY}'},
            'models': {upstream: {'name': 'Imported verification model'}}}}}))
        importer = Importer(root)
        source_id = importer.discover(file=str(file))['sources'][0]['id']
        preview = importer.preview(source_id)
        assert not preview['errors'], preview['errors']
        assert environment['CODING_FAST_API_KEY'] not in json.dumps(preview)
        mid = preview['models'][0]['id']
        values = importer.take(preview['preview_id'], [mid])
        api('POST', '/cloud/admin/models/import', json={'models': values})
        assert mid not in {m['id'] for m in api('GET', '/cloud/models?agent_id=agent-code')}
        wait_job(api('POST', '/cloud/admin/models/apply', json={})['job_id'])
        assert api('POST', '/cloud/admin/models/' + mid + '/test')['ok']
        report['checks']['jsonc_import_gateway_publish_and_real_model_test'] = True
        cat = api('GET', '/cloud/admin/catalog')
        assert environment['CODING_FAST_API_KEY'] not in json.dumps(cat)
        agent = dict(cat['agents']['agent-code']['draft'], name='Imported model Agent', bindings=[],
                     allowed_model_ids=[mid], default_model_id=mid)
        api('PUT', '/cloud/admin/agents/import-agent', json={'config': agent})
        wait_job(api('POST', '/cloud/admin/agents/import-agent/apply', json={})['job_id'])
        session = api('POST', '/session', json={'_cloud': {'agent_id': 'import-agent', 'username': 'verification'}})
        result = api('POST', f"/session/{session['id']}/message", json={'model': {'providerID': 'cloud-model-gateway', 'modelID': mid},
                     'parts': [{'type': 'text', 'text': 'Use bash to run pwd and write IMPORTED-MODEL-OK to the relative file outputs/model-result.txt. Use the default working directory: do not cd or set workdir. Then reply with exactly IMPORTED-MODEL-OK.'}]})
        assert 'IMPORTED-MODEL-OK' in '\n'.join(p.get('text', '') for p in result['parts'])
        assert session['directory'] == f"/workspace/sessions/{session['id']}"
        history = api('GET', f"/session/{session['id']}/message")
        tool_parts = [p for message in history for p in message['parts'] if p.get('type') == 'tool']
        # A provider may redirect pwd instead of printing it. Prove the actual
        # contract: default-cwd bash writes a relative artifact in this session.
        assert any(p.get('tool') == 'bash' and p.get('state', {}).get('status') == 'completed'
                   and 'outputs/model-result.txt' in p['state'].get('input', {}).get('command', '')
                   and 'workdir' not in p['state'].get('input', {})
                   and '/workspace' not in p['state']['input']['command']
                   and 'cd ' not in p['state']['input']['command'] for p in tool_parts)
        artifact = client.get('/cloud/files/download', params={'agent_id': 'import-agent', 'username': 'verification',
            'session_id': session['id'], 'path': 'outputs/model-result.txt'})
        artifact.raise_for_status()
        assert artifact.text.strip() == 'IMPORTED-MODEL-OK'
        report['checks']['real_model_default_cwd_and_artifact_download'] = True
        denied = client.post('/session/' + sid + '/prompt_async', json={'model': {'providerID': 'cloud-model-gateway', 'modelID': mid}, 'parts': []})
        assert denied.status_code == 403
        report['checks']['assigned_agent_real_call_and_unassigned_denial'] = True
        report['checks']['catalog_secret_redaction'] = True
        # A controlled interrupted gateway task must restore bytes and the prior
        # active configuration on controller restart, without changing history.
        from app.management import ManagementStore
        import base64
        store = ManagementStore(root / 'data/management', root / 'agents')
        gateway_path = root / 'data/management/gateway/config.json'
        backup = gateway_path.read_bytes()
        jid = store.new_job('models.apply', '*', {})
        store.job(jid, status='applying', gateway_backup=base64.b64encode(backup).decode())
        gateway_path.write_text('{"model_list":[]}')
        deploy.compose(root, 'restart', 'controller')
        deploy.ready(root)
        restored = api('GET', '/cloud/admin/jobs/' + jid)
        assert restored['status'] == 'failed' and gateway_path.read_bytes() == backup
        assert api('GET', '/session/' + sid)['id'] == sid
        report['checks']['interrupted_gateway_restart_recovery'] = True
        report['result'] = 'passed'
    except BaseException as exc:
        report['result'] = 'failed'
        report['error'] = type(exc).__name__
        raise
    finally:
        client.close()
        os.environ.pop('WEB_VERIFY_MODEL_KEY', None)
        if args.keep_running and report['result'] == 'passed':
            report['cleanup'] = 'Owned test stack retained for companion verification'
        else:
            try:
                deploy.stop(root)
            except Exception:
                report['cleanup'] = 'Inspect the owned instance only: ' + instance
        (ROOT / f'artifacts/web/upgrade-{version}-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
