"""Public HTTP contracts for versioned platform configuration."""
import asyncio
import copy
import json
from pathlib import Path

import httpx
from fastapi import APIRouter, Body, File, Form, UploadFile
from starlette.responses import Response

from app.management import fail, redact, identifier
from app.admin_dto import ModelWrite, ModelImport, AgentWrite, BindingWrite, ApplyRequest, CopyRequest, ResourceWrite, ProbeRequest


def create_admin_router(store, runtime):
    router = APIRouter(tags=['platform-management'])

    @router.get('/cloud/capabilities')
    def capabilities():
        return {'version': '0.2.2', 'configuration_preview': True, 'session_workspace_binding': True, 'authentication': 'bearer', 'management': True,
            'resource_kinds': ['mcp', 'skill', 'hook'], 'model_gateway': 'litellm',
            'mcp_oauth': False, 'skill_upload_limit': 20 * 1024**2}

    @router.get('/cloud/agents')
    def agents():
        _, data = store.read()
        return [{'id': aid, 'version': a['active'], **(store.agent_config(a) or {'enabled': False})}
                for aid, a in data['agents'].items()]

    @router.get('/cloud/models')
    def models(agent_id: str | None = None):
        _, data = store.read()
        active = next((v['models'] for v in data['gateway_versions'] if v['version'] == data['gateway_active']), None)
        available = active or {mid: m for mid, m in data['models'].items() if m.get('legacy')}
        if agent_id:
            a = data['agents'].get(agent_id)
            if not a:
                fail('Unknown Agent', 404)
            allowed = (store.agent_config(a) or {}).get('allowed_model_ids', [])
            available = {k: v for k, v in available.items() if k in allowed}
        return [redact(m) for m in available.values() if m.get('enabled', True)]

    @router.get('/cloud/admin/catalog')
    def catalog():
        result = store.public_catalog()
        for j in result['jobs'].values():
            j.pop('gateway_backup', None)
        return result

    @router.get('/cloud/admin/models')
    def admin_models():
        rev, data = store.read()
        return {'revision': rev, 'models': [dict(redact(m), references=store.model_references(data, mid)) for mid, m in data['models'].items()]}

    @router.put('/cloud/admin/models/{model_id}')
    def save_model(model_id: str, payload: ModelWrite):
        payload = payload.model_dump(exclude_unset=True)
        store.save_model(model_id, payload['model'], payload.get('revision'))
        return {'ok': True}

    @router.post('/cloud/admin/models/import')
    def import_models(payload: ModelImport):
        payload = payload.model_dump(exclude_unset=True)
        from app.management import validate_model, preserve_secrets
        items = payload.get('models', [])
        if not items or len(items) > 100:
            fail('Import 1–100 models at a time')
        with store.edit(payload.get('revision')) as data:
            ids = set()
            for item in items:
                mid = identifier(item.get('id'))
                if mid in ids:
                    fail('Duplicate imported model ID')
                ids.add(mid)
                if mid in data['models'] and not payload.get('replace', False):
                    fail('Model already exists: ' + mid, 409)
                value = preserve_secrets(item, data['models'].get(mid, {}))
                validate_model(value)
                if value.get('legacy') or value['provider'] == 'legacy':
                    fail('Imported models cannot claim legacy identity')
                if not value.get('enabled', True) and store.model_references(data, mid):
                    fail('Replace Agent references before disabling imported models', 409)
                data['models'][mid] = value
        return {'ok': True, 'imported': sorted(ids), 'assigned_agents': []}

    @router.post('/cloud/admin/models/apply')
    async def apply_models(payload: ApplyRequest = Body(default=ApplyRequest())):
        payload = payload.model_dump(exclude_unset=True)
        rev, data = store.read()
        if any(j['status'] in {'queued', 'validating', 'waiting', 'applying'} for j in data['jobs'].values()):
            fail('Wait for the current configuration application to finish', 409)
        if payload.get('revision', rev) != rev:
            fail('Configuration changed; reload', 409)
        models = data['models']
        if payload.get('version') is not None:
            old = next((v for v in data['gateway_versions'] if v['version'] == payload['version']), None)
            if not old:
                fail('Unknown gateway version', 404)
            models = old['models']
        for aid, agent in data['agents'].items():
            for mid in (store.agent_config(agent) or {}).get('allowed_model_ids', []):
                if mid not in models or not models[mid].get('enabled', True):
                    fail('Gateway candidate would remove a model used by ' + aid, 409)
        jid = store.new_job('models.apply', '*', {'models': copy.deepcopy(models)})
        runtime.spawn(runtime.apply_gateway(jid))
        return {'job_id': jid}

    @router.post('/cloud/admin/models/{model_id}/test')
    async def test_model(model_id: str):
        _, data = store.read()
        if model_id not in data['models']:
            fail('Model not found', 404)
        # Test the deployed model through the same gateway used by all Agents.
        if model_id not in {m['id'] for m in models()}:
            fail('Publish gateway configuration before testing this model', 409)
        try:
            result = await runtime.client.post(runtime.backend.config.model_gateway.base_url.rstrip('/') + '/chat/completions',
                json={'model': model_id, 'messages': [{'role': 'user', 'content': 'Reply with OK.'}], 'max_tokens': 32}, timeout=90)
            if result.status_code >= 400:
                return {'ok': False, 'status': result.status_code, 'error': 'Model request failed; check endpoint, credentials and model ID'}
            return {'ok': True, 'status': result.status_code}
        except httpx.HTTPError:
            return {'ok': False, 'error': 'Model request timed out or could not connect'}

    @router.delete('/cloud/admin/models/{model_id}')
    def delete_model(model_id: str, revision: int | None = None):
        with store.edit(revision) as data:
            if model_id not in data['models']:
                fail('Model not found', 404)
            refs = store.model_references(data, model_id)
            if refs:
                fail('Replace model references in these Agents first: ' + ', '.join(refs), 409)
            del data['models'][model_id]
        return {'ok': True, 'requires_gateway_publish': True}

    @router.get('/cloud/admin/agents')
    def admin_agents():
        rev, data = store.read()
        return {'revision': rev, 'agents': list(data['agents'].values())}

    @router.put('/cloud/admin/agents/{agent_id}')
    def save_agent(agent_id: str, payload: AgentWrite):
        payload = {'config': payload.config.model_dump(), 'revision': payload.revision}
        store.save_agent(agent_id, payload['config'], payload.get('revision'))
        return {'ok': True}

    @router.post('/cloud/admin/agents/{agent_id}/copy')
    def copy_agent(agent_id: str, payload: CopyRequest):
        payload = payload.model_dump(exclude_unset=True)
        store.save_agent(payload['id'], {}, payload.get('revision'), source=agent_id)
        return {'ok': True, 'id': payload['id']}

    @router.put('/cloud/admin/agents/{agent_id}/bindings')
    def bindings(agent_id: str, payload: BindingWrite):
        payload = payload.model_dump(exclude_unset=True)
        _, data = store.read()
        if agent_id not in data['agents']:
            fail('Agent not found', 404)
        cfg = copy.deepcopy(data['agents'][agent_id]['draft'])
        for name in ('bindings', 'allowed_model_ids', 'default_model_id', 'small_model_id'):
            if name in payload:
                cfg[name] = payload[name]
        store.save_agent(agent_id, cfg, payload.get('revision'))
        return {'ok': True}

    @router.get('/cloud/admin/agents/{agent_id}/effective-config')
    def effective(agent_id: str):
        _, data = store.read()
        agent = data['agents'].get(agent_id)
        if not agent:
            fail('Agent not found', 404)
        cfg = agent['draft']
        store.validate_agent(data, agent_id, cfg)
        resources = []
        for b in cfg['bindings']:
            r, v = store.resource_version(data, b['id'], b['version'])
            resources.append({'id': r['id'], 'owner': r['owner'], 'name': r['name'], 'kind': r['kind'],
                'version': v['version'], 'latest_version': len(r['versions']), 'data': redact(v['data']),
                'enabled': v['data'].get('enabled', True),
                'target_path': 'opencode.json:mcp.' + r['name'] if r['kind'] == 'mcp' else '/opt/agent/' + ('skills/' if r['kind'] == 'skill' else 'plugins/') + r['id'],
                'files': sorted(v['files'])})
        active = next((v for v in agent['versions'] if v['version'] == agent['active']), None)
        active_json = None
        if active:
            path = Path(active['path']) / 'opencode.json'
            if path.is_file():
                active_json = redact(json.loads(path.read_text(encoding='utf-8')))
        return {'agent_id': agent_id, 'active_version': agent['active'], 'active_configuration': store.agent_config(agent),
                'draft': cfg, 'resources': resources, 'active_opencode': active_json,
                'draft_opencode': runtime.compile_agent(data, agent_id, cfg, 0, preview=True)['opencode']}

    @router.post('/cloud/admin/agents/{agent_id}/config-preview')
    def preview_agent(agent_id: str, payload: AgentWrite):
        identifier(agent_id)
        _, data = store.read()
        return runtime.compile_agent(data, agent_id, payload.config.model_dump(), 0, preview=True)

    @router.get('/cloud/admin/config-preview')
    def preview_global():
        _, data = store.read()
        gateway = store.root / 'gateway/config.json'
        resources = copy.deepcopy({key: value for key, value in data['resources'].items() if not value.get('owner')})
        for resource in resources.values():
            for version in [resource.get('draft', {}), *resource.get('versions', [])]:
                version.get('data', {}).pop('sources', None)
        return {'models': redact(data['models']), 'resources': redact(resources),
                'active_gateway': redact(json.loads(gateway.read_text(encoding='utf-8'))) if gateway.is_file() else None,
                'gateway_version': data.get('gateway_active'),
                'gateway_applying': any(j['kind'] == 'models.apply' and j['status'] in {'queued', 'validating', 'waiting', 'applying'} for j in data['jobs'].values()),
                'scope': 'resource-library', 'opencode': None}

    @router.post('/cloud/admin/agents/{agent_id}/apply')
    @router.post('/cloud/admin/agents/{agent_id}/rollback')
    async def apply_agent(agent_id: str, payload: ApplyRequest = Body(default=ApplyRequest())):
        payload = payload.model_dump(exclude_unset=True)
        rev, data = store.read()
        if payload.get('revision', rev) != rev:
            fail('Configuration changed; reload', 409)
        agent = data['agents'].get(agent_id)
        if not agent:
            fail('Agent not found', 404)
        cfg = agent['draft']
        if payload.get('version'):
            version = next((v for v in agent['versions'] if v['version'] == payload['version']), None)
            if not version:
                fail('Agent version not found', 404)
            cfg = version['config']
        store.validate_agent(data, agent_id, cfg)
        available = {m['id'] for m in models()}
        if set(cfg['allowed_model_ids']) - available:
            fail('Publish selected models to the gateway first', 409)
        if any(j['status'] in {'queued', 'validating', 'waiting', 'applying'} and j['target'] in {agent_id, '*'} for j in data['jobs'].values()):
            fail('An application job is already running', 409)
        jid = store.new_job('agent.apply', agent_id, {'config': copy.deepcopy(cfg)})
        runtime.spawn(runtime.apply_agent(jid))
        return {'job_id': jid}

    @router.get('/cloud/admin/resources')
    def resources():
        rev, data = store.read()
        return {'revision': rev, 'resources': list(redact(data['resources']).values())}

    @router.put('/cloud/admin/resources/{resource_id}')
    def save_resource(resource_id: str, payload: ResourceWrite):
        payload = payload.model_dump(exclude_unset=True)
        store.save_resource(resource_id, payload['resource'], payload.get('revision'))
        return {'ok': True}

    @router.post('/cloud/admin/resources/{resource_id}/copy')
    def copy_resource(resource_id: str, payload: CopyRequest):
        payload = payload.model_dump(exclude_unset=True)
        rid = identifier(payload['id'])
        owner = payload.get('owner') or None
        with store.edit(payload.get('revision')) as data:
            if resource_id not in data['resources'] or rid in data['resources']:
                fail('Invalid source or duplicate destination', 409)
            if owner and owner not in data['agents']:
                fail('Unknown owner Agent', 404)
            resource = copy.deepcopy(data['resources'][resource_id])
            resource.update(id=rid, owner=owner, archived=False)
            data['resources'][rid] = resource
        return {'id': rid}

    @router.post('/cloud/admin/resources/{resource_id}/upload')
    async def upload_skill(resource_id: str, file: UploadFile = File(), owner: str = Form(''), revision: int | None = Form(None)):
        content = await file.read(20 * 1024**2 + 1)
        store.upload_skill(resource_id, file.filename or '', content, owner or None, revision)
        return {'ok': True}

    @router.get('/cloud/admin/resources/{resource_id}/versions')
    def versions(resource_id: str):
        _, data = store.read()
        if resource_id not in data['resources']:
            fail('Resource not found', 404)
        r = data['resources'][resource_id]
        refs = []
        for aid, a in data['agents'].items():
            if any(b['id'] == resource_id for v in a['versions'] for b in v['config']['bindings']) or any(b['id'] == resource_id for b in a['draft']['bindings']):
                refs.append(aid)
        return {**redact(r), 'references': refs}

    @router.get('/cloud/admin/resources/{resource_id}/file')
    def resource_file(resource_id: str, path: str, version: int | None = None):
        _, data = store.read()
        r = data['resources'].get(resource_id)
        if not r:
            fail('Resource not found', 404)
        content = store.resource_version(data, resource_id, version)[1] if version else r['draft']
        if path not in content['files']:
            fail('File not found', 404)
        return Response(store.file(content['files'][path]), media_type='application/octet-stream',
                        headers={'Content-Disposition': 'attachment', 'X-Content-Type-Options': 'nosniff'})

    @router.post('/cloud/admin/resources/{resource_id}/publish')
    async def publish(resource_id: str, payload: ProbeRequest = Body(default=ProbeRequest())):
        payload = payload.model_dump(exclude_unset=True)
        _, data = store.read()
        r = data['resources'].get(resource_id)
        if not r or r['archived']:
            fail('Resource is missing or archived', 404)
        original = copy.deepcopy(r['draft'])
        checked = original
        if r['kind'] == 'hook':
            checked = await runtime.compile_hook(original)
            aid = r['owner'] or payload.get('agent_id')
            if aid not in data['agents']:
                fail('Select a target Agent for Hook validation')
            candidate = copy.deepcopy(data)
            number = len(r['versions']) + 1
            candidate['resources'][resource_id]['versions'].append({'version': number, **checked})
            cfg = copy.deepcopy(data['agents'][aid]['draft'])
            cfg['bindings'] = [b for b in cfg['bindings'] if b['id'] != resource_id] + [{'id': resource_id, 'version': number}]
            path = await asyncio.to_thread(runtime.compile_agent, candidate, aid, cfg, 0)
            await runtime.probe(path)
        # Persist checked artifact only if the source draft has not changed.
        with store.edit() as latest:
            if latest['resources'][resource_id]['draft'] != original:
                fail('Draft changed during validation', 409)
            rr = latest['resources'][resource_id]
            number = len(rr['versions']) + 1
            import time
            rr['versions'].append({'version': number, 'created': time.time(), **checked})
        return {'version': number}

    @router.post('/cloud/admin/resources/{resource_id}/test')
    async def test_resource(resource_id: str, payload: ProbeRequest):
        payload = payload.model_dump(exclude_unset=True)
        _, data = store.read()
        r = data['resources'].get(resource_id)
        if not r:
            fail('Resource not found', 404)
        aid = r['owner'] or payload.get('agent_id')
        if aid not in data['agents']:
            fail('Select a target Agent')
        candidate = copy.deepcopy(data)
        version = len(r['versions']) + 1
        candidate['resources'][resource_id]['versions'].append({'version': version, **r['draft']})
        cfg = copy.deepcopy(data['agents'][aid]['draft'])
        cfg['bindings'] = [b for b in cfg['bindings'] if b['id'] != resource_id] + [{'id': resource_id, 'version': version}]
        root = await asyncio.to_thread(runtime.compile_agent, candidate, aid, cfg, 0)
        return await runtime.probe(root, mcp=r['kind'] == 'mcp')

    @router.get('/cloud/admin/jobs/{job_id}')
    def job(job_id: str):
        _, data = store.read()
        if job_id not in data['jobs']:
            fail('Job not found', 404)
        value = redact(data['jobs'][job_id])
        value.pop('gateway_backup', None)
        return value

    return router
