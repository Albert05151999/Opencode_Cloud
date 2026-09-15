"""The managed-model deployment contract shared by publish, preview and probes."""
import math
import re
from urllib.parse import urlsplit

PROVIDERS = {'openai-compatible': 'openai', 'openai': 'openai', 'anthropic': 'anthropic', 'google': 'gemini'}
ROUTER_SETTINGS = {'routing_strategy': 'simple-shuffle', 'num_retries': 2,
                   'timeout': 600, 'allowed_fails': 1, 'cooldown_time': 30,
                   'enable_pre_call_checks': True}


def deployment_entries(model, *, require_credentials=False):
    prefix = PROVIDERS.get(model.get('provider'))
    if not prefix or not model.get('id') or not model.get('upstream_model'):
        raise ValueError('Managed model requires an ID, provider and upstream model')
    deployments = model.get('deployments', [])
    if not isinstance(deployments, list) or len(deployments) > 32:
        raise ValueError('Use at most 32 upstream deployments per model')
    if deployments and (model.get('api_key') or model.get('additional_base_urls')):
        raise ValueError('Use deployments or the single API key/endpoints, not both')
    explicit = bool(deployments)
    if not explicit:
        deployments = [{'id': 'primary', 'api_key': model.get('api_key', ''), 'base_url': model.get('base_url', '')}]
        deployments += [{'id': f'extra-{i}', 'api_key': model.get('api_key', ''), 'base_url': base}
                        for i, base in enumerate(model.get('additional_base_urls', []), 1)]
    ids, entries = set(), []
    for index, deployment in enumerate(deployments):
        if not isinstance(deployment, dict) or set(deployment) - {'id', 'api_key', 'base_url', 'upstream_model', 'headers', 'enabled', 'rpm', 'tpm', 'weight'}:
            raise ValueError('Unsupported upstream deployment fields')
        did = deployment.get('id')
        if not isinstance(did, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', did) or did in ids:
            raise ValueError('Deployment IDs must be unique, using 1-64 letters, digits, hyphens or underscores')
        ids.add(did)
        if not isinstance(deployment.get('enabled', True), bool):
            raise ValueError('Deployment enabled must be a boolean')
        upstream = deployment.get('upstream_model') or model['upstream_model']
        if not isinstance(upstream, str):
            raise ValueError('Deployment upstream model must be text')
        base = deployment.get('base_url') or model.get('base_url', '')
        if not isinstance(base, str):
            raise ValueError('Deployment base URL must be text')
        if base:
            parsed = urlsplit(base)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError('Deployment URL must be HTTP(S), without credentials, query or fragment')
        key = deployment.get('api_key', '')
        if not isinstance(key, str):
            raise ValueError('Deployment API key must be text')
        headers = deployment.get('headers', {})
        if not isinstance(headers, dict) or any(not isinstance(v, str) for v in headers.values()):
            raise ValueError('Deployment headers must contain string values')
        limits = {}
        for field in ('rpm', 'tpm', 'weight'):
            value = deployment.get(field)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0 or (field != 'weight' and not isinstance(value, int)):
                    raise ValueError(f'Deployment {field} must be a positive ' + ('number' if field == 'weight' else 'integer'))
                limits[field] = value
        if not deployment.get('enabled', True):
            continue
        if require_credentials and (not key.strip() or key == '••••' or key.startswith(('${', '{env:', '{file:', 'os.environ/'))):
            raise ValueError('Configure a real API key for every enabled deployment')
        params = {**model.get('parameters', {}), 'model': prefix + '/' + upstream, 'api_key': key, **limits}
        if base:
            params['api_base'] = base
        merged_headers = {**model.get('headers', {}), **headers}
        if merged_headers:
            params['extra_headers'] = merged_headers
        # A colon cannot occur in a platform ID; this prevents cross-model collisions.
        identifier = f'{model["id"]}:{did}' if explicit else model['id'] + (f'-extra-{index}' if index else '')
        entries.append({'model_name': model['id'], 'litellm_params': params, 'model_info': {'id': identifier}})
    if not entries:
        raise ValueError('Enable at least one upstream deployment')
    return entries
