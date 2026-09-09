"""Real pinned runtime: initialization, concurrent cwd, SSE, files and recovery."""
import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
import uvicorn
from app.config import load_config
from app.files import create_files_router
from app.gateway import create_gateway_router
from app.main import create_app
from app.registry import Registry
from app.sandbox import LocalDockerBackend
from app.workspace import WorkspaceManager


async def main():
    root = Path(tempfile.mkdtemp(prefix='cloud-binding-', dir='/srv'))
    root.chmod(0o755)
    instance = 'binding-' + uuid.uuid4().hex[:12]
    shutil.copytree(ROOT/'agents', root/'agents')
    config = load_config(ROOT/'config.cfg')
    config = replace(config, platform=replace(config.platform, instance_id=instance))
    registry = Registry(root/'registry.db');registry.initialize()
    workspace = WorkspaceManager(root/'workspaces', root/'state', runtime_uid=10001, runtime_gid=10001)
    backend = LocalDockerBackend(config, registry, workspace, root/'agents')
    upstream = httpx.AsyncClient(trust_env=False, timeout=120)
    app = create_app(create_gateway_router(registry, backend, upstream),
        cloud_routers=[create_files_router(config.storage, workspace)])
    sock = socket.socket();sock.bind(('127.0.0.1',0));sock.listen();sock.setblocking(False)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app,log_level='warning',access_log=False,timeout_graceful_shutdown=2))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    checks = {};report={'instance':instance,'root':str(root),'checks':checks,'result':'running'}
    event_task = None
    try:
        while not server.started:await asyncio.sleep(.05)
        headers={'X-Cloud-Agent-ID':'agent-code','X-Cloud-Username':'binding-user'}
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',headers=headers,timeout=120,trust_env=False) as client:
            async def api(method,path,**kw):
                r=await client.request(method,path,**kw)
                r.raise_for_status()
                return r.json()
            a,b=await asyncio.gather(api('POST','/session',json={}),api('POST','/session',json={}))
            for s in (a,b):assert s['directory']==f'/workspace/sessions/{s["id"]}',s
            checks['init_readback']=True
            events=[];connected=asyncio.Event()
            async def listen():
                async with client.stream('GET','/event',timeout=None) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if line.startswith('data:'):
                            e=json.loads(line[5:]);events.append(e)
                            if e.get('type')=='server.connected':connected.set()
            event_task=asyncio.create_task(listen())
            await asyncio.wait_for(connected.wait(),10)
            async def shell(s,command):
                result=await api('POST',f'/session/{s["id"]}/shell',json={'agent':'build','command':command})
                return '\n'.join(p.get('state',{}).get('output','') for p in result['parts'])
            results=await asyncio.gather(*(shell(s,f'pwd; printf {i} > outputs/result.txt') for i,s in enumerate((a,b))))
            for s,output in zip((a,b),results):assert s['directory'] in output,output
            checks['parallel_default_cwd']=True
            running=asyncio.create_task(shell(a,'sleep 2; pwd'))
            await asyncio.sleep(.3)
            try:
                statuses=await api('GET','/session/status')
                assert statuses.get(a['id'],{}).get('type')=='busy',statuses
            finally:await running
            checks['busy_status_across_directories']=True
            for i,s in enumerate((a,b)):
                params={'agent_id':'agent-code','username':'binding-user','session_id':s['id'],'path':'outputs/result.txt'}
                r=await client.get('/cloud/files/download',params=params);r.raise_for_status();assert r.text==str(i)
                params['path']='outputs'
                assert (await api('GET','/cloud/files/list',params=params))['entries'][0]['name']=='result.txt'
            checks['artifact_download_and_isolation']=True
            data='nonempty attachment: 中文\n'.encode()
            result=await api('POST','/cloud/files/upload',data={'agent_id':'agent-code','username':'binding-user','session_id':a['id'],'relative_path':'inputs/test.txt'},files={'file':('test.txt',data)})
            assert result['size']==len(data) and result['sha256']==hashlib.sha256(data).hexdigest()
            assert hashlib.sha256(data).hexdigest() in await shell(a,'sha256sum inputs/test.txt')
            checks['nonempty_upload_exact_bytes']=True
            listing=await api('GET','/session')
            assert {a['id'],b['id']} <= {s['id'] for s in listing}
            checks['cross_directory_history_list']=True
            # Legacy session created at /workspace, with actual native history.
            endpoint=await backend.acquire('agent-code','binding-user')
            try:
                r=await upstream.post(endpoint.base_url+'/session',json={});r.raise_for_status();legacy=r.json()
                r=await upstream.post(endpoint.base_url+f'/session/{legacy["id"]}/shell',json={'agent':'build','command':'printf LEGACY-HISTORY'});r.raise_for_status()
                registry.record_session(legacy['id'],endpoint.sandbox_id,'agent-code','binding-user','sessions/'+legacy['id'])
            finally:await backend.release(endpoint)
            assert f'/workspace/sessions/{legacy["id"]}' in await shell(legacy,'pwd')
            history=await api('GET',f'/session/{legacy["id"]}/message')
            assert 'LEGACY-HISTORY' in json.dumps(history)
            checks['legacy_id_and_history_preserved']=True
            await asyncio.sleep(.2)
            event_sessions={e.get('properties',{}).get('sessionID') or e.get('properties',{}).get('info',{}).get('sessionID') or e.get('properties',{}).get('part',{}).get('sessionID') for e in events}
            assert {a['id'],b['id']} <= event_sessions,event_sessions
            checks['sse_all_directories_native_payload']=True
            event_task.cancel();await asyncio.gather(event_task,return_exceptions=True);event_task=None
            container=backend.client.containers.get(endpoint.container_id)
            await asyncio.to_thread(container.restart,timeout=5)
            assert a['directory'] in await shell(a,'pwd; cat outputs/result.txt')
            checks['sandbox_restart_binding_persists']=True
            report['sessions']=[a['id'],b['id'],legacy['id']]
            report['result']='passed'
    finally:
        if event_task:event_task.cancel();await asyncio.gather(event_task,return_exceptions=True)
        server.should_exit=True;await serving
        await upstream.aclose()
        for container in backend.client.containers.list(all=True,filters={'label':'cloud.platform_instance='+instance}):
            container.remove(force=True)
        destination=ROOT/'artifacts/web/session-binding-verification.json'
        destination.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':asyncio.run(main())
