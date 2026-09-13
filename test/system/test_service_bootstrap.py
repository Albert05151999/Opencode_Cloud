"""Boot each service from its isolated build context, using rendered configuration."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import pytest
from build_image.build import prepare_module

MODULES = ('api_gateway', 'catalog_service', 'sandbox_manager', 'file_service', 'model_gateway', 'operations', 'observability')

def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]

@pytest.mark.parametrize('module', MODULES)
def test_service_boots_without_sibling_sources(module, tmp_path):
    context, tag, config = prepare_module(module, artifacts=tmp_path / 'artifacts')
    port = free_port()
    config.update(port=port, host='127.0.0.1', data_root=str(tmp_path / 'data'), log_root=str(tmp_path / 'log'))
    config['services'] = {key: 'http://127.0.0.1:1' for key in config['services']}
    values = config['settings']
    for key in ('workspace_root', 'state_root', 'agents_root'):
        if key in values: values[key] = str(tmp_path / key)
    if 'runtime_uid' in values: values.update(runtime_uid=None, runtime_gid=None)
    if 'controller_config' in values:
        values['controller_config']['platform']['data_root'] = str(tmp_path / 'data')
        values['controller_config']['storage'].update(workspace_root=str(tmp_path / 'workspace_root'), state_root=str(tmp_path / 'state_root'))
    path = tmp_path / 'config.json'; path.write_text(json.dumps(config))
    env = {k:v for k,v in os.environ.items() if not k.startswith(('CLOUD_', 'SERVICE_', 'DATA_ROOT', 'LOG_ROOT', 'MODULE_CONFIG', 'PYTHONPATH'))}
    env.update(MODULE_CONFIG=str(path), SERVICE_TOKEN='test-internal-token', ADMIN_TOKEN='test-admin-token', PYTHONPATH=str(context),
               SERVICE_HOST='127.0.0.1', SERVICE_PORT=str(port), DATA_ROOT=str(tmp_path / 'data'), LOG_ROOT=str(tmp_path / 'log'))
    log = tmp_path / 'process.log'
    with log.open('w') as stream:
        process = subprocess.Popen([sys.executable, '-m', f'{module}.main'], cwd=context, env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail(f'{module} exited {process.returncode}:\n{log.read_text()}')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health/live', timeout=.5) as response:
                        assert response.status == 200
                        break
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    time.sleep(.1)
            else: pytest.fail(f'{module} liveness timed out:\n{log.read_text()}')
            ready_path = '/cloud/health/ready' if module == 'api_gateway' else '/health/ready'
            token = 'test-admin-token' if module == 'api_gateway' else 'test-internal-token'
            request = urllib.request.Request(f'http://127.0.0.1:{port}{ready_path}', headers={'Authorization':'Bearer ' + token})
            try:
                with urllib.request.urlopen(request, timeout=5) as response: assert response.status == 200
            except urllib.error.HTTPError as error:
                assert error.code == 503, f'{module} readiness should be 200 or explicit 503, got {error.code}'
        finally:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)


def test_live_gateway_catalog_and_log_services(tmp_path):
    """Real HTTP hops replace public auth with internal auth and retain trace context."""
    from contextlib import ExitStack
    modules = ('catalog_service', 'observability', 'api_gateway')
    ports = {module: free_port() for module in modules}
    processes = []
    logs = {}
    with ExitStack() as stack:
        try:
            for module in modules:
                context, _, config = prepare_module(module, artifacts=tmp_path / 'artifacts')
                config.update(port=ports[module], host='127.0.0.1', data_root=str(tmp_path / module / 'data'), log_root=str(tmp_path / 'log'))
                config['services'].update({key: f'http://127.0.0.1:{port}' for key,port in ports.items()})
                path = tmp_path / f'{module}.json'; path.write_text(json.dumps(config))
                env = {k:v for k,v in os.environ.items() if not k.endswith('_URL') and not k.startswith(('CLOUD_', 'SERVICE_', 'MODULE_CONFIG', 'PYTHONPATH', 'DATA_ROOT', 'LOG_ROOT'))}
                env.update(MODULE_CONFIG=str(path), SERVICE_TOKEN='network-internal', ADMIN_TOKEN='network-admin', PYTHONPATH=str(context), SERVICE_HOST='127.0.0.1')
                logs[module] = tmp_path / f'{module}.log'
                stream = stack.enter_context(logs[module].open('w'))
                process = subprocess.Popen([sys.executable, '-m', f'{module}.main'], cwd=context, env=env, stdout=stream, stderr=subprocess.STDOUT)
                processes.append(process)
                deadline = time.monotonic()+20
                while time.monotonic()<deadline:
                    if process.poll() is not None: pytest.fail(logs[module].read_text())
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{ports[module]}/health/live', timeout=.5) as response:
                            assert response.status == 200
                            break
                    except (urllib.error.URLError, TimeoutError): time.sleep(.1)
                else: pytest.fail(logs[module].read_text())
            base = f"http://127.0.0.1:{ports['api_gateway']}"
            def get(path, token='network-admin'):
                request = urllib.request.Request(base+path, headers={'Authorization':'Bearer '+token})
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.load(response), dict(response.headers)
            with pytest.raises(urllib.error.HTTPError) as rejected:
                get('/cloud/admin/provider-templates', token='network-internal')
            assert rejected.value.code == 401
            providers, headers = get('/cloud/admin/provider-templates')
            assert isinstance(providers, (dict, list)) and providers
            from config.tooling.seed import apply_seed
            seed_root = tmp_path / 'seed-config'
            seed_dir = seed_root / 'catalog_service/seeds'; seed_dir.mkdir(parents=True)
            (seed_dir / 'models.json').write_text(json.dumps({'schema_version':1,'models':[{'id':'seed-smoke','provider':'openai-compatible','upstream_model':'mock','api_key':'${SEED_KEY}'}]}))
            current_models, _ = get('/cloud/admin/models')
            imported = apply_seed(seed_root,'models.json',apply=True,catalog_url=base,token_env='ADMIN_TOKEN',revision=current_models['revision'],environ={'ADMIN_TOKEN':'network-admin','SEED_KEY':'not-a-real-upstream-key'})
            assert imported['completed'] == ['models.import'] and not imported['published']
            updated_models, _ = get('/cloud/admin/models')
            assert any(model['id']=='seed-smoke' for model in updated_models['models'])
            module_logs, _ = get('/cloud/logs/modules')
            assert 'catalog_service' in module_logs['items']
            events, _ = get('/cloud/logs?module=catalog_service')
            assert events['items'], 'Catalog request should produce structured log output'
            request_events = [item for item in events['items'] if item.get('trace_id')]
            assert request_events, 'Gateway trace context should reach catalog logging'
            gateway_events, _ = get('/cloud/logs?module=api_gateway')
            assert {item['trace_id'] for item in request_events} & {item.get('trace_id') for item in gateway_events['items']}, 'Gateway and catalog should share an actual trace ID'
        finally:
            for process in processes: process.terminate()
            for process in processes:
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
