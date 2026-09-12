"""Exercise the isolated current-form test with credentials from the local test gateway."""
import asyncio
import json
import tempfile
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import docker
import httpx
from app.providers import ProviderService
from app.management import ManagementStore
from app.management_runtime import ManagementRuntime


async def main():
    client = docker.from_env()
    gateway = client.containers.get('deploy-model-gateway-1')
    env = dict(s.split('=',1) for s in gateway.attrs['Config']['Env'] if '=' in s)
    with tempfile.TemporaryDirectory(prefix='cloud-draft-probe-',dir='/srv') as temporary:
        store = ManagementStore(Path(temporary),ROOT/'agents')
        async with httpx.AsyncClient(trust_env=False) as http:
            runtime = SimpleNamespace(store=store,client=http,gateway_container=lambda:gateway,
                backend=SimpleNamespace(client=client,config=SimpleNamespace(platform=SimpleNamespace(instance_id='draft-model-verification'))))
            runtime.gateway_configuration = lambda models,environment:ManagementRuntime.gateway_configuration(runtime,models,environment)
            model = {'id':'probe','name':'Probe','provider':'openai-compatible','upstream_model':env['CODING_FAST_MODEL'].split('/',1)[1],
                     'base_url':env['CODING_FAST_1_API_BASE'],'api_key':env['CODING_FAST_API_KEY'],'parameters':{},'enabled':True}
            before = store.read()
            result = await ProviderService(runtime).test(model)
            assert result['ok'], result
            assert store.read()==before
            assert not client.containers.list(all=True,filters={'label':'cloud.model_probe=draft-model-verification'})
            report = {'result':'passed','checks':['real current-form model call','catalog unchanged','probe container removed']}
            output = ROOT/'artifacts/web/draft-model-verification.json'
            output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(json.dumps(report),encoding='utf-8')
            print(json.dumps(report))


if __name__=='__main__':
    asyncio.run(main())
