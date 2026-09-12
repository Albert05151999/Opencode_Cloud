"""Provider templates and isolated tests of the same gateway compilation used at publish."""
import asyncio
import copy
import json
import shutil
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter

from app.admin_dto import ModelWrite
from app.management import fail, preserve_secrets, validate_model, redact


class ProviderService:
    def __init__(self, runtime):
        self.runtime = runtime
        self.limit = asyncio.Semaphore(1)

    async def test(self, model):
        _, catalog = self.runtime.store.read()
        model = preserve_secrets(copy.deepcopy(model), catalog['models'].get(model['id'], {}))
        validate_model(model)
        if model.get('legacy') or model.get('provider') == 'legacy':
            fail('Use the deployed-model test for legacy environment models')
        if not model.get('api_key'):
            fail('Enter a model API key before testing')
        model['enabled'] = True
        async with self.limit:
            configuration = self.runtime.gateway_configuration({model['id']: model}, {})
            configuration['litellm_settings'] = {'drop_params': False}
            root = self.runtime.store.root / 'model-probes' / uuid.uuid4().hex
            root.mkdir(parents=True, mode=0o700)
            path = root / 'config.json'
            path.write_text(json.dumps(configuration), encoding='utf-8')
            path.chmod(0o600)
            container = None
            try:
                gateway = await asyncio.to_thread(self.runtime.gateway_container)
                container = await asyncio.to_thread(self.runtime.backend.client.containers.run,
                    gateway.image.id, detach=True,
                    command=['--config', '/app/probe.json', '--port', '4000'],
                    volumes={str(path): {'bind': '/app/probe.json', 'mode': 'ro'}},
                    ports={'4000/tcp': ('127.0.0.1', None)}, mem_limit='1g', pids_limit=256,
                    security_opt=['no-new-privileges:true'], cap_drop=['ALL'],
                    labels={'cloud.model_probe': self.runtime.backend.config.platform.instance_id})
                await asyncio.to_thread(container.reload)
                port = container.attrs['NetworkSettings']['Ports']['4000/tcp'][0]['HostPort']
                url = 'http://127.0.0.1:' + port
                ready = False
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    try:
                        if (await self.runtime.client.get(url + '/health/liveliness', timeout=1)).is_success:
                            ready = True
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(.5)
                if not ready:
                    return {'ok': False, 'stage': 'startup', 'error': 'Isolated model gateway did not become ready'}
                response = await self.runtime.client.post(url + '/chat/completions',
                    json={'model': model['id'], 'messages': [{'role': 'user', 'content': 'Reply with OK.'}], 'max_tokens': 32}, timeout=60)
                categories = {400: 'model_or_parameters', 401: 'credentials', 403: 'model_access',
                              404: 'endpoint_or_model', 429: 'quota_or_rate_limit'}
                return {'ok': response.is_success, 'tested': 'current_form', 'published': False,
                        'status': response.status_code,
                        'error': None if response.is_success else categories.get(response.status_code, 'upstream_failure')}
            except httpx.TimeoutException:
                return {'ok': False, 'error': 'timeout', 'published': False}
            except httpx.HTTPError:
                return {'ok': False, 'error': 'connection', 'published': False}
            finally:
                try:
                    if container:
                        await asyncio.to_thread(container.remove, force=True)
                finally:
                    # Only the unique directory created by this operation is removed.
                    shutil.rmtree(root)


def create_provider_router(runtime):
    router = APIRouter(tags=['provider-configuration'])
    service = ProviderService(runtime)

    @router.get('/cloud/admin/provider-templates')
    def templates():
        return json.loads(Path(__file__).with_name('provider_templates.json').read_text(encoding='utf-8'))

    @router.post('/cloud/admin/models/test-draft')
    async def test_draft(payload: ModelWrite):
        return await service.test(payload.model.model_dump())

    @router.post('/cloud/admin/models/config-preview')
    def config_preview(payload: ModelWrite):
        model = payload.model.model_dump()
        validate_model(model)
        if model.get('legacy'):
            return {'gateway':{'model_name':model['id'],'source':'deployment environment'},'agent':{}}
        gateway = runtime.gateway_configuration({model['id']:model}, {})
        declaration = {'name':model['name'] or model['id']}
        if model.get('context') and model.get('output'):
            declaration['limit'] = {'context':model['context'],'output':model['output']}
        return redact({'gateway':gateway['model_list'],'agent':{'provider':{'cloud-model-gateway':{'models':{model['id']:declaration}}}}})

    return router
