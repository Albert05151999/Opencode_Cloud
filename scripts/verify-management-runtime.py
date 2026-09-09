"""Exercise management against real isolated Docker sandboxes and the local gateway."""
import asyncio
import configparser
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sys
import tempfile
import zipfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
import uvicorn
from app.main import build_app
from app.config import load_config


async def main():
    root = Path(tempfile.mkdtemp(prefix='cloud-web-verify-', dir='/srv'))
    root.chmod(0o755)
    shutil.copytree(ROOT / 'agents', root / 'agents')
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(ROOT / 'config.cfg')
    instance = 'webtest-' + secrets.token_hex(5)
    cfg['platform'].update(instance_id=instance, host='127.0.0.1', data_root=str(root / 'data'))
    cfg['storage'].update(workspace_root=str(root / 'workspaces'), state_root=str(root / 'state'))
    (root / 'data').mkdir()
    token = secrets.token_urlsafe(40)
    (root / 'data/admin-token').write_text(token)
    with (root / 'config.cfg').open('w') as f:
        cfg.write(f)
    config = load_config(root / 'config.cfg', environ={})
    app = build_app(config, root / 'agents')
    async def diagnose_fixture(response):
        if response.request.url.path == '/config' and response.status_code >= 400:
            await response.aread()
            print('Controlled fixture config failure:', response.text[:3000], flush=True)
    app.state.management.client.event_hooks['response'] = [diagnose_fixture]
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.setblocking(False)
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning', access_log=False))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(.1)
    report = {'root': str(root), 'instance': instance, 'result': 'running', 'checks': {}}
    class RemoteMCP(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            self.send_response(405)
            self.end_headers()
        def do_POST(self):
            if self.headers.get('Authorization') != 'Bearer remote-fixture-key':
                self.send_response(401)
                self.end_headers()
                return
            request = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
            if 'id' not in request:
                self.send_response(202)
                self.end_headers()
                return
            method = request['method']
            if method == 'initialize':
                result = {'protocolVersion': request['params']['protocolVersion'], 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'remote-test', 'version': '1'}}
            elif method == 'tools/list':
                result = {'tools': [{'name': 'echo', 'description': 'Return the remote MCP verification marker', 'inputSchema': {'type': 'object', 'properties': {}}}]}
            elif method == 'tools/call':
                result = {'content': [{'type': 'text', 'text': 'REMOTE-MCP-VERIFIED-42'}]}
            else:
                result = {}
            content = json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
    bridge = app.state.backend.client.networks.get('bridge').attrs['IPAM']['Config'][0]['Gateway']
    remote_mcp = ThreadingHTTPServer((bridge, 0), RemoteMCP)
    threading.Thread(target=remote_mcp.serve_forever, daemon=True).start()
    async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{listener.getsockname()[1]}',
                                headers={'Authorization': 'Bearer ' + token}, timeout=180, trust_env=False) as client:
        async def api(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            if response.status_code >= 400:
                raise RuntimeError(f'{method} {path} -> {response.status_code}: {response.text[:500]}')
            return response.json()
        async def wait_job(jid):
            for _ in range(240):
                j = await api('GET', '/cloud/admin/jobs/' + jid)
                if j['status'] in {'failed', 'succeeded'}:
                    assert j['status'] == 'succeeded', j
                    return j
                await asyncio.sleep(1)
            raise RuntimeError('Job timeout')
        try:
            response = await client.get('/cloud/admin/catalog', headers={'Authorization': 'Bearer invalid'})
            assert response.status_code == 401
            report['checks']['bearer'] = True
            catalog = await api('GET', '/cloud/admin/catalog')
            agent = copy.deepcopy(catalog['agents']['agent-code']['draft'])
            agent['name'] = 'Verification Agent'
            agent['bindings'] = []
            await api('PUT', '/cloud/admin/agents/verify-agent', json={'config': agent})
            skill = b'---\nname: cloud-test-skill\ndescription: A verification Skill. Load when asked to verify management.\n---\nThe verification marker is SKILL-VERIFIED-42. Include it in the final answer.\n'
            mcp_code = '''import sys,json
for line in sys.stdin:
 try:
  r=json.loads(line)
  if 'id' not in r: continue
  method=r['method']
  if method=='initialize': result={'protocolVersion':r.get('params',{}).get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'verification','version':'1'}}
  elif method=='tools/list': result={'tools':[{'name':'echo','description':'Returns the management MCP verification marker','inputSchema':{'type':'object','properties':{}}}]}
  elif method=='tools/call': result={'content':[{'type':'text','text':'MCP-VERIFIED-42'}]}
  else: result={}
  print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)
 except Exception: pass
'''
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as z:
                z.writestr('SKILL.md', skill)
                z.writestr('scripts/mcp.py', mcp_code)
            await api('POST', '/cloud/admin/resources/verify-skill/upload', files={'file': ('skill.zip', data.getvalue())})
            await api('POST', '/cloud/admin/resources/verify-skill/publish', json={})
            await api('PUT', '/cloud/admin/resources/verify-mcp', json={'resource': {'kind': 'mcp', 'name': 'verify_mcp', 'owner': None,
                'data': {'type': 'local', 'command': ['python3', '/opt/agent/skills/verify-skill/scripts/mcp.py'], 'cwd': '/workspace', 'timeout': 10000}}})
            await api('POST', '/cloud/admin/resources/verify-mcp/publish', json={})
            await api('PUT', '/cloud/admin/resources/verify-remote-mcp', json={'resource': {'kind': 'mcp', 'name': 'verify_remote', 'owner': None,
                'data': {'type': 'remote', 'url': f'http://{bridge}:{remote_mcp.server_port}/mcp', 'headers': {'Authorization': 'Bearer remote-fixture-key'}, 'oauth': False}}})
            await api('POST', '/cloud/admin/resources/verify-remote-mcp/publish', json={})
            hook = "import fs from 'node:fs'; export default async () => ({'tool.execute.after': async () => { fs.writeFileSync('/workspace/hook-proof.txt','HOOK-VERIFIED-42'); fs.appendFileSync('/workspace/hook-order.txt','A'); }});"
            await api('PUT', '/cloud/admin/resources/verify-hook', json={'resource': {'kind': 'hook', 'name': 'verify_hook', 'owner': None,
                'data': {'entry': 'hook.ts', 'sources': {'hook.ts': hook}}}})
            await api('POST', '/cloud/admin/resources/verify-hook/publish', json={'agent_id': 'verify-agent'})
            hook2 = "import fs from 'node:fs'; export default async () => ({'tool.execute.after': async () => { fs.appendFileSync('/workspace/hook-order.txt','B'); }});"
            await api('PUT', '/cloud/admin/resources/verify-hook-two', json={'resource': {'kind': 'hook', 'name': 'verify_hook_two', 'owner': None,
                'data': {'entry': 'hook.js', 'sources': {'hook.js': hook2}}}})
            await api('POST', '/cloud/admin/resources/verify-hook-two/publish', json={'agent_id': 'verify-agent'})
            report['checks']['hook_static_and_load'] = True
            agent['bindings'] = [{'id': rid, 'version': 1} for rid in ('verify-skill', 'verify-mcp', 'verify-remote-mcp', 'verify-hook', 'verify-hook-two')]
            await api('PUT', '/cloud/admin/agents/verify-agent', json={'config': agent})
            jid = (await api('POST', '/cloud/admin/agents/verify-agent/apply', json={}))['job_id']
            await wait_job(jid)
            report['checks']['agent_apply'] = True
            mcp = await api('POST', '/cloud/admin/resources/verify-mcp/test', json={'agent_id': 'verify-agent'})
            assert mcp['ok'], mcp
            report['checks']['mcp_connection'] = True
            assert (await api('POST', '/cloud/admin/resources/verify-remote-mcp/test', json={'agent_id': 'verify-agent'}))['ok']
            report['checks']['remote_mcp_header_auth_and_connection'] = True
            headers = {'X-Cloud-Agent-ID': 'verify-agent', 'X-Cloud-Username': 'verification'}
            session = await api('POST', '/session', json={'_cloud': {'agent_id': 'verify-agent', 'username': 'verification'}})
            sid = session['id']
            denied = await client.post(f'/session/{sid}/prompt_async', json={'model': {'providerID': 'cloud-model-gateway', 'modelID': 'data-fast'}, 'parts': []})
            assert denied.status_code == 403
            report['checks']['model_assignment'] = True
            message = await api('POST', f'/session/{sid}/message', json={'model': {'providerID': 'cloud-model-gateway', 'modelID': 'coding-fast'},
                'parts': [{'type': 'text', 'text': 'Load the cloud-test-skill using the skill tool. Call both the verify_mcp echo tool and the verify_remote echo tool. Execute python3 to print sum(range(1,101)). Include all three verification markers and the sum in your final answer.'}]})
            text = '\n'.join(p.get('text', '') for p in message.get('parts', []) if p.get('type') == 'text')
            assert '5050' in text and 'SKILL-VERIFIED-42' in text and 'MCP-VERIFIED-42' in text and 'REMOTE-MCP-VERIFIED-42' in text, text
            proof = root / 'workspaces/verify-agent/verification/hook-proof.txt'
            assert proof.read_text() == 'HOOK-VERIFIED-42'
            order = (proof.parent / 'hook-order.txt').read_text()
            assert order and order == 'AB' * (len(order) // 2), order
            report['checks']['hook_execution_order'] = True
            report['checks']['real_skill_mcp_hook_model'] = True
            report['session'] = sid
            # Publishing a library version does not change the Agent binding.
            await api('POST', '/cloud/admin/resources/verify-skill/upload', files={'file': ('SKILL.md', skill + b'Version two.')})
            await api('POST', '/cloud/admin/resources/verify-skill/publish', json={})
            effective = await api('GET', '/cloud/admin/agents/verify-agent/effective-config')
            assert effective['resources'][0]['version'] == 1
            report['checks']['version_pinning'] = True
            # Rollback creates a new immutable version pointing at the original content.
            agent['description'] = 'Updated draft'
            await api('PUT', '/cloud/admin/agents/verify-agent', json={'config': agent})
            await wait_job((await api('POST', '/cloud/admin/agents/verify-agent/apply', json={}))['job_id'])
            await wait_job((await api('POST', '/cloud/admin/agents/verify-agent/rollback', json={'version': 1}))['job_id'])
            history = await api('GET', f'/session/{sid}/message', headers=headers)
            assert history
            report['checks']['rollback_preserves_session'] = True
            report['result'] = 'passed'
        finally:
            remote_mcp.shutdown()
            remote_mcp.server_close()
            server.should_exit = True
            await task
            # Only containers belonging to this unique verification instance are removed.
            containers = app.state.backend.client.containers.list(all=True, filters={'label': 'cloud.platform_instance=' + instance})
            for container in containers:
                container.remove(force=True)
            (ROOT / 'artifacts/web').mkdir(exist_ok=True)
            (ROOT / 'artifacts/web/runtime-verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
