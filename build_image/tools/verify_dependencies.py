#!/usr/bin/env python3
"""Install each independent lock in a fresh venv and import only its build context."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from build_image.build import MODULES, prepare_module

def verify(module, workspace):
    context, tag, config = prepare_module(module, artifacts=workspace / 'artifacts')
    venv = workspace / 'venv'
    subprocess.run(['uv', 'venv', '--python', '3.12', str(venv)], check=True, capture_output=True)
    python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    lock = context / module / 'requirements.lock'
    subprocess.run(['uv', 'pip', 'sync', '--python', str(python), str(lock)], check=True, capture_output=True)
    config.update(data_root=str(workspace / 'data'), log_root=str(workspace / 'log'))
    for key in ('workspace_root', 'state_root', 'agents_root'):
        if key in config['settings']: config['settings'][key] = str(workspace / key)
    config['settings'].update(runtime_uid=None, runtime_gid=None)
    path = workspace / 'config.json'; path.write_text(json.dumps(config))
    environment = {k:v for k,v in os.environ.items() if not k.endswith('_URL') and not k.startswith(('CLOUD_', 'SERVICE_', 'MODULE_CONFIG', 'PYTHONPATH', 'DATA_ROOT', 'LOG_ROOT', 'WORKSPACE_ROOT', 'STATE_ROOT', 'AGENTS_ROOT'))}
    environment.update(MODULE_CONFIG=str(path), SERVICE_TOKEN='isolated-test', ADMIN_TOKEN='isolated-admin', MODEL_GATEWAY_TOKEN='isolated-inference')
    code = '''import importlib,json,pathlib,sys
sys.path.insert(0,sys.argv[1])
module=importlib.import_module(sys.argv[2]+'.main')
assert pathlib.Path(module.__file__).is_relative_to(pathlib.Path(sys.argv[1]))
assert 'app' not in sys.modules
print(json.dumps({'module':sys.argv[2],'routes':sorted({route.path for route in module.app.routes}),'source':module.__file__}))
'''
    result = subprocess.run([str(python), '-I', '-c', code, str(context), module], cwd=workspace, env=environment, check=True, capture_output=True, text=True)
    return json.loads(result.stdout.strip().splitlines()[-1])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('modules', nargs='*', default=[m for m in MODULES if m != 'agent_runtime'])
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/verification/isolated-dependencies.json')
    args = parser.parse_args()
    report = {'platform':sys.platform, 'python_target':'3.12', 'results':[]}
    failed = False
    for module in args.modules:
        if module not in MODULES or module == 'agent_runtime': parser.error('choose a Python service module')
        with tempfile.TemporaryDirectory(prefix=f'cloud-{module}-') as directory:
            try:
                row = verify(module, Path(directory)); row['result'] = 'passed'
            except subprocess.CalledProcessError as error:
                row = {'module':module, 'result':'failed', 'error': (error.stderr or error.stdout or str(error)).decode() if isinstance(error.stderr or error.stdout, bytes) else error.stderr or error.stdout or str(error)}
                failed = True
            report['results'].append(row)
            print(f"{module}: {row['result']}", flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    if failed: raise SystemExit(1)

if __name__ == '__main__': main()
