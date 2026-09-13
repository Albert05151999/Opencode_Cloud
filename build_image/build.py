#!/usr/bin/env python3
"""Explicit-context builds and source-free offline server releases (Linux amd64)."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.tooling.loader import ConfigError, load_config, render

MODULES = ('api_gateway', 'catalog_service', 'sandbox_manager', 'file_service', 'model_gateway', 'operations', 'observability', 'agent_runtime')
VERSION = (ROOT / 'VERSION').read_text().strip()

def release_version(root=ROOT):
    version = (Path(root) / 'VERSION').read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',version): raise ValueError('Invalid root VERSION')
    return version


def version_arguments(module, root=ROOT):
    root = Path(root)
    versions = json.loads((root / 'config/build_image/versions.json').read_text())
    allowed = {'NODE_VERSION','NODE_ARCHIVE_SHA256','PYTHON_VERSION','OPENCODE_VERSION','LITELLM_VERSION','UBUNTU_IMAGE','UBUNTU_SNAPSHOT','CONTROLLER_BASE_IMAGE','NGINX_IMAGE'}
    if set(versions) != allowed: raise ValueError('Missing or unsupported central build version fields')
    if module == 'model_gateway':
        lock = (root / 'model_gateway/requirements.lock').read_text()
        match = re.search(r'^litellm==([^\s\\]+)',lock,re.M)
        if not match or match[1] != versions['LITELLM_VERSION']:
            raise ValueError('LITELLM_VERSION differs from model_gateway requirements.lock; re-lock dependencies explicitly')
    if module == 'agent_runtime':
        package = json.loads((root / 'agent_runtime/image/package.json').read_text())
        lock = json.loads((root / 'agent_runtime/image/package-lock.json').read_text())
        if package['dependencies']['opencode-ai'] != versions['OPENCODE_VERSION'] or lock['packages']['node_modules/opencode-ai']['version'] != versions['OPENCODE_VERSION']:
            raise ValueError('OPENCODE_VERSION differs from npm package/lock; re-lock dependencies explicitly')
        keys = ('CONTROLLER_BASE_IMAGE','UBUNTU_IMAGE','NODE_VERSION','NODE_ARCHIVE_SHA256','OPENCODE_VERSION','UBUNTU_SNAPSHOT','PYTHON_VERSION')
    elif module == 'nginx': keys = ('NGINX_IMAGE',)
    else: keys = ('CONTROLLER_BASE_IMAGE','PYTHON_VERSION')
    return {key:versions[key] for key in keys}


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')

def run(*args):
    subprocess.run(list(map(str, args)), check=True)

def registry(root=ROOT):
    specs = json.loads((Path(root) / 'config/build_image/modules.json').read_text())
    for module, spec in specs.items():
        manifest = Path(root) / module / 'module.yaml'
        if manifest.exists():
            value = json.loads(manifest.read_text())
            if value['module_id'] != module:
                raise ValueError('module manifest identity mismatch')
            spec.update(value['build'])
            spec['version'] = value['version']
            spec['entrypoint'] = value['entrypoint']
    return specs

def safe_source(root, source):
    root = Path(root).resolve()
    path = (root / source).resolve()
    if not path.is_relative_to(root) or not path.exists():
        raise ValueError(f'invalid or missing build source: {source}')
    if path.is_dir() and any(x.is_symlink() for x in path.rglob('*')):
        raise ValueError(f'build source contains symlink: {source}')
    return path

def copy_source(root, source, output):
    path = safe_source(root, source)
    target = output / source
    target.parent.mkdir(parents=True, exist_ok=True)
    if path.is_dir():
        shutil.copytree(path, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.env', '.env.*', '.git', 'node_modules', 'docs', 'test', 'tests'), dirs_exist_ok=True)
    else:
        shutil.copy2(path, target)

def prepare_module(module, profile='production', root=ROOT, artifacts=None):
    root = Path(root)
    artifacts = Path(artifacts or root / 'artifacts')
    specs = registry(root)
    if module not in specs: raise ValueError(f'unknown module: {module}')
    spec = specs[module]
    version_args = version_arguments(module,root)
    output = artifacts / 'contexts' / module
    if output.exists(): shutil.rmtree(output)
    output.mkdir(parents=True)
    for source in spec['sources']:
        if Path(source).parts[0] not in (module, 'contracts'):
            raise ValueError(f'foreign business source prohibited: {source}')
        copy_source(root, source, output)
    shared = spec.get('shared_libs')
    if shared:
        version_path = root / 'shared_libs/VERSION'
        if not version_path.exists() or version_path.read_text().strip() != shared['version']:
            raise ValueError('shared_libs version does not match pinned build dependency')
        copy_source(root, 'shared_libs', output)
    config = render(root / 'config', module, artifacts / 'rendered_config' / profile / module, profile)
    # Rendered configuration carries secret references, never resolved credentials.
    shutil.copy2(artifacts / 'rendered_config' / profile / module / 'config.json', output / 'config.json')
    recipe = root / spec['recipe']
    shutil.copy2(recipe, output / 'Dockerfile')
    if module == 'agent_runtime':
        for name in ('runtime-config.py','runtime-log.py'):
            shutil.copy2(root / 'build_image/modules/agent_runtime' / name, output / name)
    elif module == 'nginx':
        script = root / 'build_image/nginx/nginx-entrypoint.sh'
        shutil.copy2(script, output / script.name)
    dump(output / 'build-manifest.json', {'module_id': module, 'version': spec['version'], 'sources': spec['sources'], 'shared_libs': shared, 'platform': 'linux/amd64', 'build_args': version_args})
    return output, f"opencode-cloud/{module}:{spec['version']}", config

def build_module(module, profile='production', prepare_only=False, root=ROOT, artifacts=None):
    output, tag, config = prepare_module(module, profile, root, artifacts)
    if not prepare_only:
        args = [item for key,value in version_arguments(module,root).items() for item in ('--build-arg',f'{key}={value}')]
        run('docker', 'build', '--platform', 'linux/amd64', *args, '-t', tag, output)
    return tag, config

def nginx_config(config):
    settings = config['settings']
    domain = settings['domain']
    if not re.fullmatch(r'(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?', domain):
        raise ConfigError('domain mode requires a valid config/nginx domain')
    for key in ('certificate', 'private_key'):
        if not re.fullmatch(r'/etc/nginx/tls/[a-zA-Z0-9._/-]+', settings[key]):
            raise ConfigError(f'invalid nginx {key} path')
    log_max_bytes = settings.get('log_max_bytes')
    log_backup_count = settings.get('log_backup_count')
    if isinstance(log_max_bytes, bool) or not isinstance(log_max_bytes, int) or log_max_bytes < 1024:
        raise ConfigError('nginx log_max_bytes must be an integer of at least 1024')
    if isinstance(log_backup_count, bool) or not isinstance(log_backup_count, int) or not 1 <= log_backup_count <= 20:
        raise ConfigError('nginx log_backup_count must be an integer from 1 to 20')
    return f'''events {{}}
http {{
  map $http_upgrade $connection_upgrade {{ default upgrade; '' close; }}
  map $request_id $nginx_span_id {{ "~^(?<generated_span_id>[0-9a-f]{{16}})" $generated_span_id; }}
  map $http_traceparent $incoming_trace_id {{
    default '';
    "~^00-(?<validated_incoming_trace_id>(?!0{{32}})[0-9a-f]{{32}})-[0-9a-f]{{16}}-0[01]$" $validated_incoming_trace_id;
  }}
  map $incoming_trace_id $trace_id {{ '' $request_id; default $incoming_trace_id; }}
  log_format cloud_json escape=json '{{"timestamp":"$time_iso8601","level":"INFO","module":"nginx","instance_id":"$hostname","action":"http_request","request_id":"$upstream_http_x_cloud_request_id","trace_id":"$trace_id","span_id":"$nginx_span_id","method":"$request_method","path":"$uri","status_code":$status,"bytes_sent":$bytes_sent,"duration_seconds":$request_time}}';
  access_log /log/nginx/__NGINX_INSTANCE__/events.jsonl cloud_json;
  error_log /dev/stderr warn;
  server {{
    listen 443 ssl;
    server_name {domain};
    ssl_certificate {settings['certificate']};
    ssl_certificate_key {settings['private_key']};
    client_max_body_size 0;
    location / {{
      proxy_pass http://api_gateway:18080;
      proxy_http_version 1.1;
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header traceparent "00-$trace_id-$nginx_span_id-01";
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection $connection_upgrade;
      proxy_buffering off;
      proxy_request_buffering off;
      proxy_read_timeout 3600s;
    }}
  }}
}}
'''

def compose_document(tags, configs, mode):
    services = {}
    for module, tag in tags.items():
        if module in ('agent_runtime', 'nginx'): continue
        config = configs[module]
        env = {'MODULE_CONFIG': '/config/config.json', 'SERVICE_TOKEN': '${SERVICE_TOKEN:?set SERVICE_TOKEN in .env}',
               'SERVICE_PORT': str(config['port']), 'DATA_ROOT': config['data_root'], 'LOG_ROOT': '/log'}
        env.update({key.upper() + '_URL': value for key, value in config['services'].items()})
        service = {'image': tag, 'restart': 'unless-stopped', 'environment': env,
                   'volumes': [f'./config/{module}/config.json:/config/config.json:ro', f'./data/{module}:{config["data_root"]}', './log:/log'],
                   'healthcheck': {'test': ['CMD', 'python', '-c', f"import os,urllib.request; urllib.request.urlopen('http://' + os.environ.get('SERVICE_HOST','127.0.0.1') + ':{config['port']}/health/live')"], 'interval': '15s', 'timeout': '5s', 'retries': 5}}
        if module in ('model_gateway', 'sandbox_manager'): env['MODEL_GATEWAY_TOKEN'] = '${MODEL_GATEWAY_TOKEN:?set MODEL_GATEWAY_TOKEN in .env}'
        if module == 'catalog_service': env['AGENT_RUNTIME_IMAGE'] = tags['agent_runtime']
        if module == 'api_gateway': env['ADMIN_TOKEN'] = '${ADMIN_TOKEN:?set ADMIN_TOKEN in .env}'
        if module == 'api_gateway' and mode == 'ip': service['ports'] = [f"${{API_PORT:-18080}}:{config['port']}"]
        service['extra_hosts'] = ['host.docker.internal:host-gateway']
        env['SANDBOX_MANAGER_URL'] = f"http://host.docker.internal:{configs['sandbox_manager']['port']}"
        if module != 'api_gateway':
            host = '${DOCKER_BRIDGE_IP:?run install.sh to detect Docker bridge}' if module == 'model_gateway' else '127.0.0.1'
            service['ports'] = [f"{host}:{config['port']}:{config['port']}"]
            if module == 'model_gateway': service['ports'].append(f"127.0.0.1:{config['port']}:{config['port']}")
        if module in ('sandbox_manager', 'file_service'):
            workspace = '${DEPLOY_ROOT:?set DEPLOY_ROOT}/data/workspaces'
            state = '${DEPLOY_ROOT:?set DEPLOY_ROOT}/data/file_service/state'
            agents = '${DEPLOY_ROOT:?set DEPLOY_ROOT}/data/sandbox_manager/agents'
            service['volumes'].extend([f'{workspace}:{workspace}', f'{state}:{state}'])
            env['WORKSPACE_ROOT'] = workspace
            env['STATE_ROOT'] = state
            env['HOST_WORKSPACE_ROOT'] = workspace
        if module == 'sandbox_manager':
            service['volumes'].extend(['/var/run/docker.sock:/var/run/docker.sock', f'{agents}:{agents}'])
            env['AGENTS_ROOT'] = agents
            host_logs = '${DEPLOY_ROOT:?set DEPLOY_ROOT}/log'
            env['HOST_LOG_ROOT'] = host_logs
            service['volumes'].append(f'{host_logs}:{host_logs}')
            env['SERVICE_HOST'] = '${DOCKER_BRIDGE_IP:?run install.sh to detect Docker bridge}'
            env['AGENT_RUNTIME_IMAGE'] = tags['agent_runtime']
            env.update({key.upper() + '_URL': f"http://127.0.0.1:{configs[key]['port']}" for key in configs if key not in ('agent_runtime', 'nginx')})
            service['network_mode'] = 'host'
            service.pop('ports', None)
        services[module] = service
    if mode == 'domain':
        nginx_settings = configs['nginx']['settings']
        services['nginx'] = {'image': tags['nginx'], 'restart': 'unless-stopped', 'ports': ['${HTTPS_PORT:-443}:443'],
                             'environment': {'LOG_ROOT': '/log', 'NGINX_LOG_MAX_BYTES': str(nginx_settings['log_max_bytes']), 'NGINX_LOG_BACKUP_COUNT': str(nginx_settings['log_backup_count'])},
                             'volumes': ['./config/nginx/nginx.conf:/etc/nginx/nginx.conf:ro', './config/nginx/tls:/etc/nginx/tls:ro', './log:/log'],
                             'healthcheck': {'test': ['CMD', 'wget', '--quiet', '--no-check-certificate', '--output-document=/dev/null', 'https://127.0.0.1/cloud/health'], 'interval': '10s', 'timeout': '5s', 'retries': 6, 'start_period': '10s'}}
    return {'services': services}

def preflight_bundle(profile='production', mode='ip', root=ROOT):
    """Reject inconsistent deployment contracts before preparing or building any image."""
    from urllib.parse import urlsplit
    root = Path(root)
    configs = {module: load_config(root / 'config', module, profile) for module in MODULES}
    controller = configs['sandbox_manager']['settings']['controller_config']
    if controller['sandbox']['opencode_internal_port'] != configs['agent_runtime']['port']:
        raise ConfigError('agent_runtime port must match sandbox_manager controller_config.sandbox.opencode_internal_port')
    catalog_url = configs['catalog_service']['settings']['model_gateway_public_url'].rstrip('/')
    sandbox_url = controller['model_gateway']['base_url'].rstrip('/')
    if catalog_url != sandbox_url:
        raise ConfigError('catalog_service model_gateway_public_url must match sandbox_manager controller_config.model_gateway.base_url')
    endpoint = urlsplit(catalog_url)
    if endpoint.scheme not in ('http','https') or not endpoint.hostname or endpoint.path != '/v1':
        raise ConfigError('Runtime model gateway URL must be an HTTP(S) /v1 endpoint')
    if endpoint.hostname in ('host.docker.internal','model_gateway','127.0.0.1','localhost'):
        if (endpoint.port or (443 if endpoint.scheme == 'https' else 80)) != configs['model_gateway']['port']:
            raise ConfigError('Runtime model gateway URL port must match model_gateway configured port')
    for module,config in configs.items():
        for target,url in config['services'].items():
            endpoint = urlsplit(url)
            if target in configs and endpoint.hostname == target:
                if (endpoint.port or (443 if endpoint.scheme == 'https' else 80)) != configs[target]['port']:
                    raise ConfigError(f'{module}.services.{target} port differs from target module port')
    for module in MODULES:
        version_arguments(module,root)
    if mode == 'domain':
        nginx_config(load_config(root / 'config','nginx',profile))
        version_arguments('nginx',root)
    return configs


def include_seed_tools(root, release):
    """Ship stdlib CLI and public seed templates, never local env files or user seed data."""
    from config.tooling.seed import read_seed
    root,release = Path(root),Path(release)
    package = release / 'tooling/config'
    (package / 'tooling').mkdir(parents=True,exist_ok=True)
    (package / '__init__.py').write_text('"""Offline release configuration tools."""\n')
    for source in (root / 'config/tooling').glob('*.py'):
        if source.is_symlink(): raise ValueError('Seed tooling source cannot be a symlink')
        shutil.copy2(source,package / 'tooling' / source.name)
    seed_name = 'models.example.json'
    read_seed(root / 'config',seed_name)  # Reject accidental cleartext credential edits before bundling.
    source = root / 'config/catalog_service/seeds' / seed_name
    if source.is_symlink(): raise ValueError('Seed example cannot be a symlink')
    target = release / 'config/catalog_service/seeds' / seed_name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)
    example = root / 'config/catalog_service/.env.example'
    if example.is_symlink(): raise ValueError('Environment example cannot be a symlink')
    # The distribution template permits instructions and blank assignments only.
    for line in example.read_text().splitlines():
        line=line.strip()
        if line and not line.startswith('#') and ('=' not in line or line.split('=',1)[1].strip()):
            raise ValueError('catalog .env.example must contain blank assignments only; keep local credentials in .env')
    shutil.copy2(example,release / 'config/catalog_service/.env.example')


def bundle(profile='production', mode='ip', prepare_only=False, root=ROOT, artifacts=None, docker_materials=None):
    root = Path(root); artifacts = Path(artifacts or root / 'artifacts')
    version = release_version(root)
    preflight_bundle(profile,mode,root)
    release = artifacts / 'releases' / version
    if release.exists(): shutil.rmtree(release)
    release.mkdir(parents=True)
    tags, configs = {}, {}
    for module in MODULES:
        tags[module], configs[module] = build_module(module, profile, prepare_only, root, artifacts)
        render(root / 'config', module, release / 'config' / module, profile)
    if mode == 'domain':
        config = render(root / 'config', 'nginx', release / 'config/nginx', profile)
        (release / 'config/nginx/nginx.conf').write_text(nginx_config(config).replace('api_gateway:18080', f"api_gateway:{configs['api_gateway']['port']}"))
        tags['nginx'], configs['nginx'] = build_module('nginx', profile, prepare_only, root, artifacts)
    dump(release / 'compose.json', compose_document(tags, configs, mode))
    include_seed_tools(root,release)
    scripts = artifacts / 'scripts/server'; scripts.mkdir(parents=True, exist_ok=True)
    for source in (root / 'build_image/bundle').glob('*.sh'):
        shutil.copy2(source, release / source.name); shutil.copy2(source, scripts / source.name)
        (release / source.name).chmod(0o755); (scripts / source.name).chmod(0o755)
    shutil.copy2(root / 'build_image/docker/install-docker.sh', release / 'install-docker.sh')
    shutil.copy2(root / 'build_image/docker/install-docker.sh', scripts / 'install-docker.sh')
    if docker_materials:
        shutil.copytree(docker_materials, release / 'docker', dirs_exist_ok=True)
    (release / '.env.example').write_text('SERVICE_TOKEN=\nADMIN_TOKEN=\nMODEL_GATEWAY_TOKEN=\nDEPLOY_ROOT=\nCOMPOSE_PROJECT_NAME=opencode_cloud\nAPI_PORT=18080\nHTTPS_PORT=443\nDOCKER_BRIDGE_IP=\n')
    dump(release / 'manifest.json', {'version': version, 'profile': profile, 'mode': mode, 'platform': 'linux/amd64', 'images': tags, 'prepared_only': prepare_only})
    if prepare_only: return release
    (release / 'images').mkdir()
    for module, tag in tags.items():
        archive = artifacts / 'images' / module / version / 'image.tar'
        archive.parent.mkdir(parents=True, exist_ok=True)
        run('docker', 'save', '-o', archive, tag)
        shutil.copy2(archive, release / 'images' / f'{module}.tar')
    files = sorted(p for p in release.rglob('*') if p.is_file())
    (release / 'SHA256SUMS').write_text(''.join(f'{file_hash(p)}  {p.relative_to(release)}\n' for p in files))
    with tarfile.open(artifacts / 'releases' / f'release-{version}.tar.gz', 'w:gz') as tar:
        tar.add(release, arcname=f'release-{version}')
    return release

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('module', 'bundle'):
        item = sub.add_parser(name)
        if name == 'module': item.add_argument('module', choices=MODULES + ('nginx',))
        else:
            item.add_argument('--mode', choices=('ip', 'domain'), default='ip')
            item.add_argument('--docker-materials', type=Path)
        item.add_argument('--profile', default='production')
        item.add_argument('--prepare-only', action='store_true', help='render contexts/config/scripts without claiming built images')
    a = p.parse_args()
    if a.command == 'module': print(build_module(a.module, a.profile, a.prepare_only)[0])
    else: print(bundle(a.profile, a.mode, a.prepare_only, docker_materials=a.docker_materials))

if __name__ == '__main__': main()
