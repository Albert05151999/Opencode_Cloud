"""Explicit seed application through existing catalog APIs; never runs on startup."""
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
REF = re.compile(r'^\$\{([A-Z][A-Z0-9_]*)\}$')
ENV_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def read_env_file(path):
    """Parse a small dotenv subset as data, without expansion or shell execution."""
    values = {}
    for number, raw_line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        if '=' not in line:
            raise ValueError(f'Invalid env file syntax at line {number}')
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if not ENV_NAME.fullmatch(key):
            raise ValueError(f'Invalid env variable name at line {number}')
        if value.startswith(('"', "'")):
            quote = value[0]
            if len(value) < 2 or value[-1] != quote:
                raise ValueError(f'Invalid quoted env value at line {number}')
            value = value[1:-1]
        else:
            # A comment begins only after whitespace, so URL fragments and
            # literal '#' characters remain intact. Values are never expanded.
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
        values[key] = value
    return values


def read_seed(root, name):
    directory = (Path(root) / 'catalog_service/seeds').resolve()
    path = (directory / name).resolve()
    if not path.is_relative_to(directory): raise ValueError('Seed path must remain within config/catalog_service/seeds')
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) - {'schema_version','models','templates'} or value.get('schema_version') != 1:
        raise ValueError('Seed must use schema_version 1 with models and/or templates')
    models, templates = value.get('models',[]), value.get('templates',[])
    if not isinstance(models,list) or not isinstance(templates,list) or not models and not templates:
        raise ValueError('Seed requires nonempty models or templates lists')
    if len(models)>100 or len(templates)>100: raise ValueError('Seed exceeds 100 models/templates')
    ids = []
    for model in models:
        if not isinstance(model,dict) or not ID.fullmatch(model.get('id','')): raise ValueError('Invalid seed model ID')
        if model.get('provider') not in {'openai','openai-compatible','anthropic','google'} or not model.get('upstream_model'):
            raise ValueError('Seed models require managed provider and upstream_model')
        ids.append(model['id'])
    if len(ids)!=len(set(ids)): raise ValueError('Duplicate seed model ID')
    for template in templates:
        if not isinstance(template,dict) or set(template)-{'template_id','agent_id','models','resources'}:
            raise ValueError('Invalid template restore fields')
        if not all(ID.fullmatch(template.get(key,'')) for key in ('template_id','agent_id')): raise ValueError('Invalid template/Agent ID')
    def check_secrets(item):
        if isinstance(item,dict):
            for key, child in item.items():
                if key in {'api_key','token','password'} and child and not REF.fullmatch(str(child)):
                    raise ValueError('Seed credentials must use environment references')
                if key in {'headers','environment','extra_headers'} and child:
                    if not isinstance(child,dict) or any(not REF.fullmatch(str(v)) for v in child.values()):
                        raise ValueError('Seed header/environment values must use environment references')
                check_secrets(child)
        elif isinstance(item,list):
            for child in item: check_secrets(child)
    check_secrets(value)
    return value


def resolve(value, environ, *, optional=False):
    if isinstance(value,dict):
        result = {}
        for key, item in value.items():
            if key == 'deployments' and isinstance(item, list):
                result[key] = [resolve(d, environ, optional=isinstance(d, dict) and d.get('enabled') is False) for d in item]
            else:
                result[key] = resolve(item, environ, optional=optional)
        return result
    if isinstance(value,list): return [resolve(item,environ,optional=optional) for item in value]
    if isinstance(value,str) and (match:=REF.fullmatch(value)):
        if optional and not environ.get(match[1]): return ''
        if not environ.get(match[1]): raise ValueError(f'Missing seed environment reference: {match[1]}')
        return environ[match[1]]
    return value


def apply_seed(root,name,*,apply=False,catalog_url=None,token_env='ADMIN_TOKEN',revision=None,replace=False,environ=None,env_file=None,request=None):
    seed = read_seed(root,name)
    report = {'mode':'apply' if apply else 'dry-run','model_ids':[item['id'] for item in seed.get('models',[])],
              'template_restores':[{'template_id':item['template_id'],'agent_id':item['agent_id']} for item in seed.get('templates',[])],
              'replace_models':replace,'published':False,'completed':[]}
    if not apply: return report
    parsed = urllib.parse.urlsplit(catalog_url or '')
    if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('--apply requires an explicit HTTP(S) --catalog-url without embedded credentials')
    if seed.get('models') and (not isinstance(revision,int) or revision<0): raise ValueError('Model seed apply requires --revision from GET /cloud/admin/models')
    if not ENV_NAME.fullmatch(token_env): raise ValueError('Invalid authentication environment variable name')
    process_environ = os.environ if environ is None else environ
    # Explicit process values win over the convenience file. Neither source is
    # included in reports or error messages.
    resolved_environ = read_env_file(env_file) if env_file else {}
    resolved_environ.update(process_environ)
    if not resolved_environ.get(token_env): raise ValueError(f'Missing authentication environment variable: {token_env}')
    # Resolve every reference before the first write; failures never print payloads or credentials.
    seed = resolve(seed,resolved_environ)
    def send(path,payload):
        if request: return request(path,payload)
        req = urllib.request.Request(catalog_url.rstrip('/')+path,data=json.dumps(payload).encode(),
              headers={'Authorization':'Bearer '+resolved_environ[token_env],'Content-Type':'application/json'},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=30) as response: return json.load(response)
        except urllib.error.HTTPError as exc: raise ValueError(f'Catalog returned HTTP {exc.code}; no automatic retry. Completed steps: {report["completed"]}') from None
        except urllib.error.URLError: raise ValueError(f'Catalog connection failed; inspect server state before retry. Completed steps: {report["completed"]}') from None
    if seed.get('models'):
        send('/cloud/admin/models/import',{'models':seed['models'],'replace':replace,'revision':revision})
        report['completed'].append('models.import')
    for template in seed.get('templates',[]):
        tid = template['template_id']; payload={key:value for key,value in template.items() if key!='template_id'}
        send(f'/cloud/admin/agent-templates/{tid}/restore',payload)
        report['completed'].append('template.restore:'+template['agent_id'])
    return report
