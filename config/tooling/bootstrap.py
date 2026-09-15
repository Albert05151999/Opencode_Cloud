"""Compile dotenv presets and initialize an installation through public APIs."""
import argparse
import copy
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from config.tooling.deployment_env import DEFAULTS
from config.tooling.seed import read_env_file, read_seed, resolve, ID


def presets(config_root, values):
    values = {**DEFAULTS, **values}
    seed = read_seed(config_root, 'models.minimax-glm.json')
    models = []
    for model, prefix in zip(seed['models'], ('MINIMAX', 'ZAI')):
        accounts = []
        for index, account in enumerate(model['deployments']):
            key = prefix + '_API_KEY' + ('_2' if index else '')
            if values.get(key):
                account['enabled'] = True
                accounts.append(account)
        if accounts:
            model['deployments'] = accounts
            models.append(resolve(model, values))
    agents = []
    for entry in filter(None, (v.strip() for v in values['PRESET_AGENTS'].split(','))):
        kind, separator, model = entry.partition(':')
        if not separator or kind not in ('code', 'data') or model not in {m['id'] for m in models}:
            raise ValueError('PRESET_AGENTS requires code:model_id or data:model_id with a configured model')
        if any(a['agent_id'] == 'agent-' + kind for a in agents):
            raise ValueError('Duplicate PRESET_AGENTS entry')
        agents.append({'template_id': 'example-' + kind, 'agent_id': 'agent-' + kind,
                       'models': {'glm' if kind == 'code' else 'minimax': model}})
    if values['BOOTSTRAP_BUNDLE'] and (models or agents):
        raise ValueError('Use BOOTSTRAP_BUNDLE or model keys/PRESET_AGENTS, not both initialization sources')
    return {'schema_version': 1, 'models': models, 'templates': agents}


class Client:
    def __init__(self, url, token):
        self.url, self.token = url, token
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def __call__(self, path, payload=None, method=None, content_type='application/json'):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.url + path, data=body, method=method,
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': content_type})
        try:
            with self.opener.open(req, timeout=180) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # Never echo response bodies, which can contain submitted credentials.
            raise ValueError(f'Initialization request {path} failed: HTTP {error.code}; inspect management jobs') from None

    def publish(self, path, payload=None):
        result = self(path, payload or {})
        if not result.get('job_id'):
            return result
        for _ in range(300):
            job = self('/cloud/admin/jobs/' + result['job_id'])
            if job['status'] == 'succeeded':
                return job
            if job['status'] in ('failed', 'cancelled', 'needs_recovery', 'interrupted'):
                raise ValueError(f'Initialization publish failed: job {result["job_id"]}; inspect its error in the management page')
            time.sleep(1)
        raise ValueError('Initialization publish timed out; inspect management jobs before retrying')


def initialize(root, client=None):
    root = Path(root)
    values = {**DEFAULTS, **read_env_file(root / '.env')}
    seed = presets(root / 'config', values)
    bundle = root / values['BOOTSTRAP_BUNDLE'] if values['BOOTSTRAP_BUNDLE'] else None
    content = bundle.read_bytes() if bundle else b''
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True).encode() + content).hexdigest()
    state_path = root / 'data/bootstrap.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'digest': digest, 'completed': []}
    if state['digest'] != digest:
        raise ValueError('Initialization configuration changed. Use the management import workflow to change an existing installation.')
    if 'done' in state['completed']:
        print('Initialization already complete; existing configuration retained.')
        return
    client = client or Client('http://127.0.0.1:' + values['API_PORT'], values['ADMIN_TOKEN'])

    def checkpoint(name, action):
        if name in state['completed']:
            return
        action()
        state['completed'].append(name)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state), encoding='utf-8')
        temporary.replace(state_path)

    if bundle:
        def restore_bundle():
            boundary = 'opencode-bootstrap-upload'
            body = b'--' + boundary.encode() + b'\r\nContent-Disposition: form-data; name="file"; filename="config.json"\r\nContent-Type: application/json\r\n\r\n' + content + b'\r\n'
            if values['BOOTSTRAP_PASSWORD']:
                body += b'--' + boundary.encode() + b'\r\nContent-Disposition: form-data; name="password"\r\n\r\n' + values['BOOTSTRAP_PASSWORD'].encode() + b'\r\n'
            body += b'--' + boundary.encode() + b'--\r\n'
            preview = client('/cloud/admin/imports/preview', body, content_type='multipart/form-data; boundary=' + boundary)
            if any(i.get('error') or i.get('conflict') for i in preview['items']):
                raise ValueError('Initialization bundle has invalid entries or ID conflicts; inspect it in the management import preview')
            result = client('/cloud/admin/imports/' + preview['preview_id'] + '/commit', {'selections': [
                {'key': i['key'], 'target_id': i['id'], 'replace': False} for i in preview['items']]})
            state['restored_templates'] = result['agent_templates']
        checkpoint('bundle.import', restore_bundle)
    elif seed['models']:
        def import_models():
            current = client('/cloud/admin/models')
            existing = {m['id'] for m in current['models']}
            if existing & {m['id'] for m in seed['models']}:
                raise ValueError('Initialization models already exist without a checkpoint; inspect existing configuration before retrying')
            client('/cloud/admin/models/import', {'models': seed['models'], 'revision': current['revision']})
        checkpoint('models.import', import_models)
    if seed['models'] or bundle:
        checkpoint('models.publish', lambda: client.publish('/cloud/admin/models/apply'))
    for preset in seed['templates']:
        aid = preset['agent_id']
        checkpoint(aid + '.restore', lambda p=preset: client('/cloud/admin/agent-templates/' + p['template_id'] + '/restore',
            {k: v for k, v in p.items() if k != 'template_id'}))
        checkpoint(aid + '.publish', lambda a=aid: client.publish('/cloud/admin/agents/' + a + '/apply'))
    if bundle:
        catalog = client('/cloud/admin/catalog')
        templates = {t['id']: t for t in client('/cloud/admin/agent-templates')}
        selected = [templates[tid] for tid in state.get('restored_templates', [])
                    if templates[tid].get('source_version', 'draft') == 'draft']
        for template in selected:
            aid = template.get('source_agent', template.get('source_id', template['id']))
            if not ID.fullmatch(aid):
                raise ValueError('Restored Agent ID is invalid')
            draft = copy.deepcopy(template['config'])
            draft['bindings'] = []
            checkpoint(aid + '.draft', lambda a=aid, d=draft: client('/cloud/admin/agents/' + a, {'config': d}, method='PUT'))
        for rid in catalog['resources']:
            target = selected[0].get('source_agent', selected[0].get('source_id')) if selected else None
            checkpoint('resource.' + rid, lambda r=rid, a=target: client.publish('/cloud/admin/resources/' + r + '/publish', {'agent_id': a} if a else {}))
        for template in selected:
            aid = template.get('source_agent', template.get('source_id', template['id']))
            cfg = copy.deepcopy(template['config'])
            for binding in cfg['bindings']:
                binding['version'] = 1
            checkpoint(aid + '.restore', lambda a=aid, c=cfg: client('/cloud/admin/agents/' + a, {'config': c}, method='PUT'))
            checkpoint(aid + '.publish', lambda a=aid: client.publish('/cloud/admin/agents/' + a + '/apply'))
    checkpoint('done', lambda: None)
    print('Initialization complete.' if seed['models'] or bundle else 'Platform ready; no presets configured. Create models and Agents in the management page.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    try:
        initialize(args.root)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')
