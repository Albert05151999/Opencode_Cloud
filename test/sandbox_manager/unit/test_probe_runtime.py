import asyncio
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException
from sandbox_manager.probes import ProbeRunner

class Container:
    id='probe-container'
    attrs={'NetworkSettings':{'Ports':{'4097/tcp':[{'HostPort':'50123'}]}},'State':{'Status':'running','ExitCode':0}}
    def reload(self):pass
    def remove(self,**kwargs):self.removed=True

class Docker:
    def __init__(self):self.container=Container();self.containers=self;self.kwargs=None
    def run(self,*args,**kwargs):self.kwargs=kwargs;return self.container


def test_probe_uses_shared_sources_writable_log_and_configured_port(tmp_path,monkeypatch):
    monkeypatch.setenv('HOST_LOG_ROOT',str(tmp_path/'log'))
    backend=SimpleNamespace(client=Docker(),config=SimpleNamespace(sandbox=SimpleNamespace(image='runtime:test',opencode_internal_port=4097,start_timeout_seconds=120),platform=SimpleNamespace(instance_id='test')))
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={}))) as client:
            result=await ProbeRunner(backend,client,tmp_path/'shared-agents/.validation').probe(tmp_path/'bundle')
            assert result=={'ok':True}
    asyncio.run(run())
    call=backend.client.kwargs
    assert call['ports']=={'4097/tcp':('127.0.0.1',None)}
    assert call['read_only'] and call['environment']['RUNTIME_LOG_DIR']=='/runtime-log'
    log_path=next(Path(source) for source,mount in call['volumes'].items() if mount['bind']=='/runtime-log')
    assert log_path.is_relative_to(tmp_path/'log/agent_runtime')
    assert (log_path/'probe-evidence.json').exists() and log_path.stat().st_mode&0o777==0o755
    assert backend.client.container.removed
    for source,mount in call['volumes'].items():
        if mount['bind'] in ('/workspace','/state/opencode'):assert Path(source).is_relative_to(tmp_path/'shared-agents/.validation')


def test_probe_detects_exited_runtime_and_keeps_evidence(tmp_path):
    backend=SimpleNamespace(client=Docker(),config=SimpleNamespace(sandbox=SimpleNamespace(image='runtime:test',opencode_internal_port=4097,start_timeout_seconds=120),platform=SimpleNamespace(instance_id='test')))
    backend.client.container.attrs={**Container.attrs,'State':{'Status':'exited','ExitCode':1}}
    async def run():
        async with httpx.AsyncClient() as client:
            with pytest.raises(HTTPException) as error:await ProbeRunner(backend,client,tmp_path).probe(tmp_path/'bundle')
            assert error.value.status_code==422 and 'exited' in error.value.detail
    asyncio.run(run())
    assert list(tmp_path.rglob('probe-evidence.json')) and backend.client.container.removed
