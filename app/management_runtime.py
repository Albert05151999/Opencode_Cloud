"""Compile immutable Agent versions and apply them through owned Docker resources."""
from __future__ import annotations

import asyncio
import configparser
import copy
import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from app.agents import AgentCatalog, AgentDefinitionError
from app.management import ManagementStore, fail, redact


class ManagedCatalog:
    def __init__(self, runtime):
        self.runtime = runtime

    def load(self, agent_id):
        _, data = self.runtime.store.read()
        agent = data['agents'].get(agent_id)
        if not agent or agent['active'] is None:
            raise AgentDefinitionError('Agent has no active configuration')
        version = next(v for v in agent['versions'] if v['version'] == agent['active'])
        path = Path(version['path'])
        original = (self.runtime.store.agents_root / agent_id).resolve()
        port = urlparse(self.runtime.backend.config.model_gateway.base_url).port or 80
        url = 'http://host.docker.internal:4001/v1' if path.resolve() == original else f'http://host.docker.internal:{port}/v1'
        return AgentCatalog(path.parent, gateway_url=url).load(agent_id)


class ManagementRuntime:
    def __init__(self, store, backend, client):
        self.store, self.backend, self.client = store, backend, client
        self.lock = asyncio.Lock()
        self.blocked = set()
        self.requests = {}
        self.acquiring = {}
        self.tasks = set()
        from app.operations import Operations
        self.operations = Operations(self)
        from app.load_tests import LoadTests
        self.load_tests = LoadTests(self)
        self.backend.workspaces.user_guard = self.load_tests.resources_for
        self.backend.agent_catalog = ManagedCatalog(self)

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def close(self):
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

    def authorize(self, agent_id, method, path, payload):
        _, data = self.store.read()
        agent = data['agents'].get(agent_id)
        if not agent:
            fail('Unknown Agent', 404)
        if agent.get('lifecycle') == 'deleting':
            fail('Agent deletion is pending; inspect the operation result', 409)
        active = self.store.agent_config(agent)
        if not active:
            fail('Publish this Agent before starting a session', 409)
        mutation = method not in {'GET', 'HEAD', 'OPTIONS', 'DELETE'}
        abort = path.endswith('/abort')
        response = bool(re.search(r'/(?:permissions/[^/]+|permission/[^/]+/reply|question/[^/]+/(?:reply|reject))$', path))
        if agent_id in self.blocked and not abort and not response:
            fail('Agent configuration is being applied; retry shortly', 503)
        if mutation and not abort and not response:
            if agent_id in self.blocked:
                fail('Agent configuration is being applied; retry shortly', 503)
            if agent.get('lifecycle') == 'archived':
                fail('Agent is archived; restore it before generating', 409)
            if any(j['status'] in {'queued', 'validating', 'waiting', 'applying'} and j['target'] == agent_id and j['kind'].startswith(('sandbox.', 'agent.archive', 'agent.restore', 'agent.delete')) for j in data['jobs'].values()):
                fail('An operation is pending for this Agent; retry after completion', 409)
            if not active.get('enabled', True):
                fail('Agent is disabled; history remains available', 409)
            if hasattr(self, 'operations'):
                self.operations.recovery.invalidate_idle(agent_id)
        # Platform-managed provider configuration must not be bypassed by native writes.
        if method not in {'GET', 'HEAD', 'OPTIONS'} and (path in {'config', 'global/config'} or path.startswith(('auth/', 'mcp/', 'provider/'))):
            fail('Use the versioned management API for configuration changes', 403)
        if isinstance(payload, dict) and mutation and re.search(r'/session/[^/]+/(message|prompt_async|command|shell)$', '/' + path) and not payload.get('model'):
            chosen = {'providerID': 'cloud-model-gateway', 'modelID': active['default_model_id']}
            payload['model'] = 'cloud-model-gateway/' + active['default_model_id'] if path.endswith('/command') else chosen
        model = payload.get('model') if isinstance(payload, dict) else None
        if not model and isinstance(payload, dict) and ('providerID' in payload or 'modelID' in payload):
            model = {'providerID': payload.get('providerID'), 'modelID': payload.get('modelID')}
        if model:
            if isinstance(model, str):
                provider, _, mid = model.partition('/')
            elif isinstance(model, dict):
                provider, mid = model.get('providerID'), model.get('modelID')
            else:
                fail('Invalid model selection')
            if provider != 'cloud-model-gateway' or mid not in active['allowed_model_ids']:
                fail('Model is not assigned to this Agent', 403)
        return mutation and not abort and not response

    def lease(self, aid, begin):
        self.requests[aid] = max(0, self.requests.get(aid, 0) + (1 if begin else -1))

    async def records(self, targets):
        return [r for r in await asyncio.to_thread(self.backend.registry.list_sandboxes) if r.agent_id in targets]

    async def idle(self, targets):
        if any(self.requests.get(a, 0) or self.acquiring.get(a, 0) for a in targets):
            return False
        for record in await self.records(targets):
            endpoint = await self.backend.inspect(record.agent_id, record.username)
            if not endpoint:
                continue
            try:
                from app.session_binding import directory_collection
                statuses = await directory_collection(self.client, self.backend.registry, endpoint)
                if any(s.get('type') in {'busy', 'retry'} for s in statuses.values()):
                    return False
            except (httpx.HTTPError, ValueError):
                fail('Cannot determine running session state; application stopped', 503)
        return True

    async def drain(self, targets):
        deadline = time.monotonic() + 120
        while not await self.idle(targets):
            if time.monotonic() >= deadline:
                fail('Timed out waiting for active tasks; draft retained', 409)
            await asyncio.sleep(1)

    async def remove_sandboxes(self, targets):
        for record in await self.records(targets):
            container = await self.backend._get_container(record.container_id) if record.container_id else None
            if container:
                self.backend._verify_ownership(container, record.agent_id, record.username)
                await self.backend._remove_owned(container)

    def compile_agent(self, data, aid, cfg, version, *, preview=False):
        self.store.validate_agent(data, aid, cfg)
        root = self.store.root / 'compiled' / (uuid.uuid4().hex) / aid
        if not preview:
            root.mkdir(parents=True)
            root.chmod(0o755)
            for p in ('global/opencode', 'skills', 'plugins'):
                (root / p).mkdir(parents=True, exist_ok=True)
            (root / 'global/opencode/.gitignore').write_text('*\n')
            trace = self.store.agents_root / 'agent-code/plugins/trace.mjs'
            shutil.copyfile(trace, root / 'plugins/system-trace.mjs')
            (root / 'AGENTS.md').write_text(cfg.get('instructions', ''), encoding='utf-8')
        plugin = ['file:///opt/agent/plugins/system-trace.mjs']
        mcp, sources = {}, []
        for binding in cfg['bindings']:
            resource, rv = self.store.resource_version(data, binding['id'], binding['version'])
            name = rv['data'].get('name', resource['name'])
            source = {'id': resource['id'], 'owner': resource['owner'], 'kind': resource['kind'],
                      'name': name, 'version': rv['version']}
            if resource['kind'] == 'mcp':
                mcp[name] = copy.deepcopy(rv['data'])
                cwd = mcp[name].pop('cwd', None)
                if cwd and mcp[name]['type'] == 'local':
                    # OpenCode's native local MCP has no cwd field. Change it only
                    # in the sandbox child process, without shell interpolation.
                    mcp[name]['command'] = ['python3', '-c',
                        'import os,sys; os.chdir(sys.argv[1]); os.execvp(sys.argv[2],sys.argv[2:])',
                        cwd, *mcp[name]['command']]
                source['path'] = 'mcp.' + name
            else:
                directory = ('skills/' if resource['kind'] == 'skill' else 'plugins/') + resource['id']
                if not preview:
                    for relative, digest in rv['files'].items():
                        dest = root / directory / relative
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(self.store.file(digest))
                        dest.chmod(0o644)
                source['path'] = '/opt/agent/' + directory
                if resource['kind'] == 'hook':
                    plugin.append('file:///opt/agent/' + directory + '/' + rv['data'].get('compiled_entry', rv['data']['entry']))
            sources.append(source)
        models = {}
        for mid in cfg['allowed_model_ids']:
            model = data['models'][mid]
            models[mid] = {'name': model.get('name', mid)}
            if model.get('context') and model.get('output'):
                models[mid]['limit'] = {'context': model['context'], 'output': model['output']}
        gateway_port = urlparse(self.backend.config.model_gateway.base_url).port or 80
        opencode = {'$schema': 'https://opencode.ai/config.json', 'share': 'disabled', 'autoupdate': False,
            'lsp': False, 'permission': 'allow', 'plugin': plugin, 'instructions': ['/opt/agent/AGENTS.md'],
            'skills': {'paths': ['/opt/agent/skills']}, 'mcp': mcp,
            'enabled_providers': ['cloud-model-gateway'], 'model': 'cloud-model-gateway/' + cfg['default_model_id'],
            'provider': {'cloud-model-gateway': {'npm': '@ai-sdk/openai-compatible', 'name': 'Cloud Model Gateway',
                'options': {'baseURL': f'http://host.docker.internal:{gateway_port}/v1'}, 'models': models}}}
        if cfg.get('small_model_id'):
            opencode['small_model'] = 'cloud-model-gateway/' + cfg['small_model_id']
        if preview:
            return {'opencode': redact(opencode), 'sources': sources}
        (root / 'opencode.json').write_text(json.dumps(opencode, ensure_ascii=False, indent=2), encoding='utf-8')
        config = self.backend.config
        ini = configparser.ConfigParser(interpolation=None)
        ini['agent'] = {'id': aid, 'display_name': cfg['name'], 'image': config.sandbox.image,
                        'idle_timeout_seconds': str(config.sandbox.idle_timeout_seconds)}
        ini['resources'] = {'cpu_limit': str(config.sandbox.default_cpu),
            'memory_mb': str(config.sandbox.default_memory_mb), 'pids_limit': str(config.sandbox.default_pids)}
        ini['models'] = {'default': cfg['default_model_id'], 'allowed': ','.join(cfg['allowed_model_ids'])}
        with (root / 'agent.cfg').open('w', encoding='utf-8') as stream:
            ini.write(stream)
        (root / 'effective.json').write_text(json.dumps({'version': version, 'sources': sources,
            'config': redact(opencode)}, ensure_ascii=False, indent=2), encoding='utf-8')
        AgentCatalog(root.parent, gateway_url=f'http://host.docker.internal:{gateway_port}/v1').load(aid)
        return root

    async def probe(self, path, *, mcp=False):
        """A disposable, unprivileged runtime with separate workspace and state."""
        config = self.backend.config
        temp = self.store.root / 'probes' / uuid.uuid4().hex
        temp.mkdir(parents=True)
        for name in ('workspace', 'state'):
            (temp / name).mkdir()
            (temp / name).chmod(0o777)
        container = None
        try:
            container = await asyncio.to_thread(self.backend.client.containers.run,
                config.sandbox.image, detach=True, user='10001:10001', read_only=True,
                labels={'cloud.management_probe': config.platform.instance_id},
                tmpfs={'/tmp': 'rw,nosuid,nodev,size=256m'}, mem_limit='1g', pids_limit=256, nano_cpus=1_000_000_000,
                cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
                volumes={str(path): {'bind': '/opt/agent', 'mode': 'ro'},
                         str(temp / 'workspace'): {'bind': '/workspace', 'mode': 'rw'},
                         str(temp / 'state'): {'bind': '/state/opencode', 'mode': 'rw'}},
                extra_hosts={'host.docker.internal': 'host-gateway'},
                ports={'4096/tcp': ('127.0.0.1', None)})
            await asyncio.to_thread(container.reload)
            port = container.attrs['NetworkSettings']['Ports']['4096/tcp'][0]['HostPort']
            url = 'http://127.0.0.1:' + port
            for _ in range(60):
                try:
                    response = await self.client.get(url + '/global/health', timeout=2)
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.5)
            else:
                fail('Isolated runtime did not start; check Hook syntax and runtime dependencies', 422)
            response = await self.client.get(url + '/config', timeout=20)
            response.raise_for_status()
            if mcp:
                response = await self.client.get(url + '/mcp', timeout=120)
                response.raise_for_status()
                states = response.json()
                if any(v.get('status') != 'connected' for v in states.values()):
                    # Provider errors can echo credential URLs; keep diagnostics categorical.
                    return {'ok': False, 'mcp': {k: {'status': v.get('status'),
                        'error': 'Check URL, credentials, installed executable and timeout'} for k, v in states.items()}}
                tools = await self.client.get(url + '/experimental/tool/ids', timeout=15)
                return {'ok': True, 'mcp': states, 'tools': tools.json() if tools.status_code == 200 else []}
            return {'ok': True}
        except httpx.HTTPError:
            fail('Runtime probe failed; check extension configuration', 422)
        finally:
            if container:
                await asyncio.to_thread(container.remove, force=True)
            # Retain paths for diagnosis; do not delete user uploads or shared directories.

    async def compile_hook(self, draft):
        directory = self.store.root / 'hook-checks' / uuid.uuid4().hex
        directory.mkdir(parents=True)
        directory.chmod(0o755)
        for p, digest in draft['files'].items():
            destination = directory / p
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(self.store.file(digest))
        # node:module strips TypeScript without evaluating source. Validation is inside
        # an unprivileged, network-disabled container; stdout is captured, never logged.
        compiler = r'''
import fs from 'node:fs'; import path from 'node:path'; import {stripTypeScriptTypes} from 'node:module';
import {spawnSync} from 'node:child_process';
const root='/source'; const result={};
function visit(dir){for(const n of fs.readdirSync(dir)){const p=path.join(dir,n); if(fs.statSync(p).isDirectory())visit(p); else {
const relative=path.relative(root,p); let code=fs.readFileSync(p,'utf8');
if(p.endsWith('.ts'))code=stripTypeScriptTypes(code,{mode:'transform'});
if(/\brequire\s*\(|\bimport\s*\(/.test(code))throw Error('Dynamic imports are unsupported');
for(const m of code.matchAll(/(?:from\s*|import\s*)['"]([^'"]+)['"]/g)){
const id=m[1]; if(!id.startsWith('node:')&&!id.startsWith('./')&&!id.startsWith('../'))throw Error('External dependencies are unsupported');
if(id.startsWith('.')){const resolved=path.resolve(path.dirname(p),id);if(!resolved.startsWith(root+'/')||!fs.existsSync(resolved))throw Error('Invalid relative import');}}
const check=spawnSync(process.execPath,['--input-type=module','--check'],{input:code,encoding:'utf8'});
if(check.status!==0)throw Error('Invalid JavaScript/TypeScript syntax'); result[relative]=code;
}}} try{visit(root);process.stdout.write(JSON.stringify({files:result}));}catch(e){process.stdout.write(JSON.stringify({error:e.message}));process.exitCode=1;}
'''
        container = None
        try:
            container = await asyncio.to_thread(self.backend.client.containers.create,
                self.backend.config.sandbox.image, entrypoint=['node', '--input-type=module', '-e'], command=[compiler],
                user='10001:10001', network_disabled=True, read_only=True, mem_limit='256m', pids_limit=64,
                cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
                volumes={str(directory): {'bind': '/source', 'mode': 'ro'}})
            await asyncio.to_thread(container.start)
            status = await asyncio.to_thread(container.wait, timeout=30)
            result = json.loads(await asyncio.to_thread(container.logs, stdout=True, stderr=False))
            if status['StatusCode'] or result.get('error'):
                fail(result.get('error', 'Hook static validation failed'), 422)
            checked = copy.deepcopy(draft)
            # Keep .ts extension: pinned OpenCode/Bun loads stripped JS from it too.
            checked['files'] = {p: self.store.blob(code.encode()) for p, code in result['files'].items()}
            return checked
        finally:
            if container:
                await asyncio.to_thread(container.remove, force=True)

    async def apply_agent(self, jid):
        async with self.lock:
            _, data = self.store.read()
            job = data['jobs'][jid]
            aid, cfg = job['target'], copy.deepcopy(job['payload']['config'])
            old = data['agents'][aid]['active']
            self.blocked.add(aid)
            try:
                self.store.job(jid, status='validating', old_active=old)
                number = len(data['agents'][aid]['versions']) + 1
                root = await asyncio.to_thread(self.compile_agent, data, aid, cfg, number)
                await self.probe(root, mcp=False)
                self.store.job(jid, status='waiting')
                await self.drain({aid})
                self.store.job(jid, status='applying')
                await self.remove_sandboxes({aid})
                with self.store.edit() as updated:
                    agent = updated['agents'][aid]
                    agent['versions'].append({'version': number, 'created': time.time(), 'config': cfg, 'path': str(root)})
                    agent['active'] = number
                    updated['jobs'][jid].update(status='succeeded', result={'version': number})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.store.job(jid, status='failed', error=exc.detail if isinstance(exc, HTTPException) else 'Application failed; previous version retained')
            finally:
                self.blocked.discard(aid)

    def gateway_container(self):
        found = self.backend.client.containers.list(all=True, filters={'label': [
            'com.docker.compose.project=' + self.backend.config.platform.instance_id,
            'com.docker.compose.service=model-gateway']})
        if len(found) != 1:
            fail('Expected exactly one model gateway for this platform instance', 409)
        return found[0]

    def gateway_configuration(self, models, environment):
        entries = []
        for model in models.values():
            if not model.get('enabled', True):
                continue
            mid = model['id']
            if model.get('legacy'):
                prefix = mid.upper().replace('-', '_')
                if prefix + '_MODEL' not in environment:
                    fail('Original gateway environment is missing model ' + mid)
                for index in (1, 2):
                    entries.append({'model_name': mid, 'litellm_params': {'model': environment[prefix + '_MODEL'],
                        'api_base': environment[prefix + f'_{index}_API_BASE'], 'api_key': environment[prefix + '_API_KEY']},
                        'model_info': {'id': mid + '-' + str(index)}})
            else:
                prefix = {'openai-compatible': 'openai', 'openai': 'openai', 'anthropic': 'anthropic', 'google': 'gemini'}[model['provider']]
                params = {'model': prefix + '/' + model['upstream_model'], 'api_key': model.get('api_key', ''), **model.get('parameters', {})}
                if model.get('base_url'):
                    params['api_base'] = model['base_url']
                if model.get('headers'):
                    params['extra_headers'] = model['headers']
                entries.append({'model_name': mid, 'litellm_params': params, 'model_info': {'id': mid}})
                for index, base in enumerate(model.get('additional_base_urls', []), 1):
                    entries.append({'model_name':mid, 'litellm_params':{**params,'api_base':base}, 'model_info':{'id':mid+'-extra-'+str(index)}})
        return {'model_list': entries, 'router_settings': {'routing_strategy': 'least-busy', 'num_retries': 2,
                'timeout': 600, 'allowed_fails': 1, 'cooldown_time': 30},
                'litellm_settings': {'callbacks': ['prometheus', 'cloud_logging.cloud_logger'], 'drop_params': False},
                'general_settings': {'disable_spend_logs': True}}

    async def apply_gateway(self, jid):
        async with self.lock:
            _, data = self.store.read()
            targets = set(data['agents'])
            self.blocked.update(targets)
            backup = None
            try:
                self.store.job(jid, status='waiting')
                await self.drain(targets)
                container = await asyncio.to_thread(self.gateway_container)
                await asyncio.to_thread(container.reload)
                environment = dict(x.split('=', 1) for x in container.attrs['Config']['Env'] if '=' in x)
                models = data['jobs'][jid]['payload']['models']
                generated = self.gateway_configuration(models, environment)
                # The gateway always mounts this directory after installation of the Web revision.
                directory = self.store.root / 'gateway'
                directory.mkdir(exist_ok=True)
                active = directory / 'config.json'
                backup = active.read_bytes() if active.exists() else None
                if not any(m.get('Destination') == '/app/managed' for m in container.attrs.get('Mounts', [])):
                    fail('Upgrade deployment scripts before publishing gateway configuration', 409)
                self.store.job(jid, status='applying', gateway_backup=base64_text(backup))
                temporary = directory / (jid + '.json')
                temporary.write_text(json.dumps(generated), encoding='utf-8')
                temporary.chmod(0o600)
                temporary.replace(active)
                await asyncio.to_thread(container.restart, timeout=10)
                for _ in range(60):
                    try:
                        response = await self.client.get(self.backend.config.model_gateway.health_url, timeout=2)
                        if response.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(1)
                else:
                    fail('Gateway readiness failed after configuration update', 503)
                with self.store.edit() as updated:
                    version = len(updated['gateway_versions']) + 1
                    updated['gateway_versions'].append({'version': version, 'models': models, 'created': time.time()})
                    updated['gateway_active'] = version
                    updated['jobs'][jid].update(status='succeeded', gateway_backup=None, result={'version': version})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if backup is not None:
                    (self.store.root / 'gateway/config.json').write_bytes(backup)
                    try:
                        await asyncio.to_thread(container.restart, timeout=10)
                    except Exception:
                        self.store.job(jid, status='failed', error='Gateway rollback could not restart; check deployment', gateway_backup=None)
                        return
                self.store.job(jid, status='failed', error=exc.detail if isinstance(exc, HTTPException) else 'Gateway update failed', gateway_backup=None)
            finally:
                self.blocked.difference_update(targets)

    async def recover(self):
        self.load_tests.store.recover()
        _, data = self.store.read()
        for jid, job in data['jobs'].items():
            if job['status'] in {'queued', 'validating', 'waiting', 'applying'}:
                if job['kind'].startswith(('sandbox.', 'agent.archive', 'agent.restore', 'agent.delete')):
                    await self.operations.reconcile(jid)
                    continue
                if job.get('gateway_backup'):
                    import base64
                    (self.store.root / 'gateway/config.json').write_bytes(base64.b64decode(job['gateway_backup']))
                    container = await asyncio.to_thread(self.gateway_container)
                    await asyncio.to_thread(container.restart, timeout=10)
                self.store.job(jid, status='failed', error=('Interrupted by controller restart; inspect actual operation state before retrying' if job['kind'].startswith(('sandbox.', 'agent.archive', 'agent.restore', 'agent.delete')) else 'Interrupted by controller restart; previous version restored'), gateway_backup=None)


def base64_text(value):
    import base64
    return base64.b64encode(value).decode() if value is not None else None
