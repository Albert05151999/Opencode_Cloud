"""Windows -> local same-origin service -> owned Linux test stack, including SSE."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', type=Path)
    args = parser.parse_args()
    if args.serve:
        import uvicorn
        from local_web.server import create_local_app
        uvicorn.run(create_local_app(args.serve), host='127.0.0.1', port=18767, log_level='warning', access_log=False)
        return
    assert os.name == 'nt', 'Run with the Windows companion virtual environment'
    import httpx
    from keyring.backends.Windows import WinVaultKeyring
    upgrade = json.loads((ROOT / 'artifacts/web/upgrade-verification.json').read_text())
    assert upgrade['result'] == 'passed' and 'retained' in upgrade.get('cleanup', '')
    command = ['wsl', '-d', 'Ubuntu-24.04', '-u', 'root', '--']
    token = subprocess.check_output(command + ['cat', upgrade['root'] + '/data/admin-token']).decode().strip()
    keepalive = subprocess.Popen(command + ['cat'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    container = json.loads(subprocess.check_output(command + ['docker', 'inspect', upgrade['instance'] + '-model-gateway-1']))[0]
    environment = dict(v.split('=', 1) for v in container['Config']['Env'] if '=' in v)
    root = Path(tempfile.mkdtemp(prefix='opencode-companion-'))
    cfg = root / 'opencode.jsonc'
    upstream = environment['CODING_FAST_MODEL'].removeprefix('openai/')
    cfg.write_text(json.dumps({'provider': {'windows': {'npm': '@ai-sdk/openai-compatible',
        'options': {'baseURL': environment['CODING_FAST_1_API_BASE'], 'apiKey': '{env:WEB_COMPANION_TEST_KEY}'},
        'models': {upstream: {'name': 'Windows imported model'}}}}}), encoding='utf-8')
    child_env = dict(os.environ, WEB_COMPANION_TEST_KEY=environment['CODING_FAST_API_KEY'])
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve', str(root)], env=child_env)
    url = 'http://127.0.0.1:18082'
    vault = WinVaultKeyring()
    previous = vault.get_password('opencode-cloud-web', url)
    report = {'result': 'running', 'checks': {}, 'server_instance': upgrade['instance']}
    client = httpx.Client(base_url='http://127.0.0.1:18767', timeout=180, trust_env=False)
    def api(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f'{method} {path} -> {response.status_code}: {response.text[:300]}')
        return response.json() if response.content else {}
    def wait_job(jid):
        for _ in range(240):
            result = api('GET', '/remote/cloud/admin/jobs/' + jid)
            if result['status'] in {'succeeded', 'failed'}:
                assert result['status'] == 'succeeded', result.get('error')
                return
            time.sleep(1)
        raise RuntimeError('Job timeout')
    try:
        for _ in range(100):
            try:
                boot = api('GET', '/local/bootstrap')
                break
            except httpx.HTTPError:
                time.sleep(.1)
        else:
            raise RuntimeError('Local service startup timed out')
        client.headers['X-Local-CSRF'] = boot['csrf']
        api('PUT', '/local/connection', json={'url': url, 'token': token, 'remember': True})
        assert vault.get_password('opencode-cloud-web', url) == token
        assert token not in (root / 'connection.json').read_text()
        for attempt in range(60):
            ready = httpx.get(url + '/cloud/health/ready', headers={'Authorization': 'Bearer ' + token}, timeout=5, trust_env=False)
            if ready.status_code == 200:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Test stack readiness: ' + ready.text)
        assert api('POST', '/local/connection/test')['capabilities']['management']
        schema = api('GET', '/remote/openapi.json')
        assert 'ModelWrite' in schema['components']['schemas']
        (ROOT / 'artifacts/web/controller-openapi.json').write_text(json.dumps(schema, indent=2), encoding='utf-8')
        assert client.get('/chat').status_code == 200
        report['checks']['compiled_page_same_origin_and_windows_vault'] = True
        sources = api('POST', '/local/opencode/discover', json={'file': str(cfg)})['sources']
        source = next(s for s in sources if Path(s['path']).resolve() == cfg.resolve())
        preview = api('POST', '/local/opencode/preview', json={'source_id': source['id']})
        assert not preview['errors'], preview['errors']
        assert environment['CODING_FAST_API_KEY'] not in json.dumps(preview)
        mid = preview['models'][0]['id']
        api('POST', '/local/opencode/import', json={'preview_id': preview['preview_id'], 'selected': [mid], 'replace': True})
        wait_job(api('POST', '/remote/cloud/admin/models/apply', json={})['job_id'])
        api('PUT', '/remote/cloud/admin/agents/windows-agent', json={'config': {'name': 'Windows verification', 'enabled': True,
            'instructions': 'Complete tasks using the available tools. Work in the requested session directory.',
            'allowed_model_ids': [mid], 'default_model_id': mid, 'bindings': []}})
        wait_job(api('POST', '/remote/cloud/admin/agents/windows-agent/apply', json={})['job_id'])
        report['checks']['windows_jsonc_environment_import_and_publish'] = True
        sid = api('POST', '/remote/session', json={'_cloud': {'agent_id': 'windows-agent', 'username': 'windows-test'}})['id']
        attachment = api('POST', '/remote/cloud/files/upload', data={'agent_id': 'windows-agent', 'username': 'windows-test',
            'session_id': sid, 'relative_path': 'inputs/numbers.txt'}, files={'file': ('numbers.txt', b'13\n18\n')})
        headers = {'X-Cloud-Agent-ID': 'windows-agent', 'X-Cloud-Username': 'windows-test', 'Accept': 'text/event-stream'}
        event_types, done, submitted, apply_job = set(), False, 0, None
        with client.stream('GET', '/remote/event', headers=headers, timeout=180) as stream:
            stream.raise_for_status()
            assert stream.headers['content-type'].startswith('text/event-stream')
            deadline = time.monotonic() + 240
            for line in stream.iter_lines():
                if time.monotonic() > deadline:
                    raise RuntimeError('SSE verification deadline exceeded')
                if not line.startswith('data:'):
                    continue
                event = json.loads(line[5:])
                event_types.add(event['type'])
                if event['type'] == 'server.connected' and not submitted:
                    api('POST', f'/remote/session/{sid}/prompt_async', json={'messageID': 'msg_' + uuid.uuid4().hex,
                        'model': {'providerID': 'cloud-model-gateway', 'modelID': mid}, 'parts': [{'type': 'text',
                        'text': f"Read {attachment['path']} using Python, sum the numbers, sleep for 10 seconds using time.sleep(10), then write exactly WINDOWS-COMPANION-OK 31 to /workspace/sessions/{sid}/output.txt. Reply with WINDOWS-COMPANION-OK and the sum. Execute the task, do not just describe it."}]})
                    submitted += 1
                props = event.get('properties', {})
                part = props.get('part', {})
                if part.get('sessionID') == sid and part.get('type') == 'tool' and part.get('state', {}).get('status') == 'running' and not apply_job:
                    apply_job = api('POST', '/remote/cloud/admin/agents/windows-agent/apply', json={})['job_id']
                if submitted and props.get('sessionID') == sid and (event['type'] == 'session.idle' or event['type'] == 'session.status' and props.get('status', {}).get('type') == 'idle'):
                    assert apply_job, 'Expected real tool execution before configuration application'
                    wait_job(apply_job)
                    done = True
                    break
        assert done and submitted == 1
        history = api('GET', f'/remote/session/{sid}/message')
        assert any('WINDOWS-COMPANION-OK' in p.get('text', '') for m in history for p in m['parts'])
        params = {'agent_id': 'windows-agent', 'username': 'windows-test', 'session_id': sid, 'path': 'output.txt'}
        artifact = client.get('/remote/cloud/files/download', params=params)
        assert artifact.status_code == 200 and artifact.text.strip() == 'WINDOWS-COMPANION-OK 31'
        report['checks']['real_sse_single_submission_history_and_tool_events'] = 'message.part.updated' in event_types
        report['checks']['chat_attachment_upload_and_artifact_download'] = True
        report['checks']['publish_waits_for_running_tool_with_sse_open'] = True
        report['session'] = sid
        report['event_types'] = sorted(event_types)
        subprocess.run(['node', 'e2e/capture-real.mjs', sid], cwd=ROOT / 'web', check=True)
        report['checks']['browser_real_chat_and_admin'] = True
        report['result'] = 'passed'
    finally:
        client.close()
        process.terminate()
        process.wait(timeout=15)
        keepalive.stdin.close()
        keepalive.wait(timeout=10)
        if previous is None:
            try:
                vault.delete_password('opencode-cloud-web', url)
            except Exception:
                pass
        else:
            vault.set_password('opencode-cloud-web', url, previous)
        (ROOT / 'artifacts/web/windows-companion-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
