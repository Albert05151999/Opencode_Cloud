"""Probe a fresh, isolated upstream server; always terminate the owned process group."""
import json
import os
from pathlib import Path
import signal
import sys
import socket
import subprocess
import tempfile
import time
import urllib.request

root = Path(__file__).resolve().parents[1]
pins = dict(line.split('=', 1) for line in (root / 'versions.env').read_text().splitlines() if '=' in line)
artifacts = root / 'artifacts/opencode'
artifacts.mkdir(parents=True, exist_ok=True)
stabilized = '--stabilized' in sys.argv
config_check = '--config-check' in sys.argv
assert subprocess.check_output(['opencode', '--version'], text=True).strip() == pins['OPENCODE_VERSION']
with socket.socket() as probe:
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    probe.bind(('127.0.0.1', 4096))
with tempfile.TemporaryDirectory(prefix='cloud-opencode-') as work:
    env = os.environ.copy()
    for key, subdir in [('HOME', 'home'), ('XDG_DATA_HOME', 'data'), ('XDG_CONFIG_HOME', 'config'), ('XDG_CACHE_HOME', 'cache')]:
        env[key] = str(Path(work) / subdir)
        Path(env[key]).mkdir()
    with (artifacts / 'server.log').open('w') as log:
        command = ['opencode', 'serve', '--hostname', '127.0.0.1', '--port', '4096']
        if stabilized or config_check:
            env['OPENCODE_CONFIG'] = str(root / 'runtime/opencode/global/opencode.json')
            env['OPENCODE_HOSTNAME'] = '127.0.0.1'
            command = ['bash', str(root / 'runtime/entrypoint.sh')]
            if stabilized:
                command = ['strace', '-f', '-e', 'trace=network', '-o', str(artifacts / 'startup-network.trace')] + command
        process = subprocess.Popen(command, cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 60
            while True:
                if process.poll() is not None:
                    raise RuntimeError('OpenCode exited; inspect server.log')
                try:
                    with urllib.request.urlopen('http://127.0.0.1:4096/global/health', timeout=2) as response:
                        health = json.load(response)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise TimeoutError('OpenCode did not become healthy')
                    time.sleep(0.2)
            assert health['healthy'] is True and health['version'] == pins['OPENCODE_VERSION'], health
            (artifacts / 'health.json').write_text(json.dumps(health, indent=2) + '\n')
            if stabilized:
                time.sleep(10)
                print(json.dumps({'health': health, 'observation_seconds_after_health': 10}))
            if config_check:
                with urllib.request.urlopen('http://127.0.0.1:4096/config', timeout=30) as response:
                    config = json.load(response)
                assert config['share'] == 'disabled' and config['autoupdate'] is False
                assert config['lsp'] is False and config.get('plugin', []) == []
                (artifacts / 'effective-config.json').write_text(json.dumps(config, indent=2) + '\n')
                print('effective-config-passed')
            if not stabilized:
                with urllib.request.urlopen('http://127.0.0.1:4096/doc', timeout=10) as response:
                    spec = json.load(response)
                assert spec['openapi'].startswith('3.') and '/session' in spec['paths']
                (artifacts / 'openapi.json').write_text(json.dumps(spec, indent=2) + '\n')
                print(json.dumps({'health': health, 'openapi': spec['openapi'], 'paths': len(spec['paths']), 'result': 'passed'}))
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
if stabilized:
    trace = (artifacts / 'startup-network.trace').read_text()
    attempts = [line for line in trace.splitlines() if any(call in line for call in ('connect(', 'sendto(', 'sendmsg(')) and ('AF_INET' in line)]
    report = {'result': 'passed' if not attempts else 'failed', 'inet_outbound_attempts': attempts,
              'scope': 'Fresh state; startup and health only; 10 second observation after readiness. LSP disabled; model execution not tested.'}
    (artifacts / 'startup-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    assert not attempts, 'Unexpected network attempts; inspect startup-network.trace'
