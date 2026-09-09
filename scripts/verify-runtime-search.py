"""Verify OpenCode text search with Docker networking disabled."""
import json
import os
import tempfile
from contextlib import closing
from pathlib import Path

import docker

ROOT = Path(__file__).resolve().parents[1]
PROBE = '''
import json, time, urllib.request
from pathlib import Path
for attempt in range(100):
    try:
        urllib.request.urlopen('http://127.0.0.1:4096/global/health', timeout=0.25).read()
        break
    except Exception:
        time.sleep(0.1)
else:
    raise RuntimeError('OpenCode not ready')
with urllib.request.urlopen('http://127.0.0.1:4096/find?pattern=OFFLINE_SEARCH_MARKER', timeout=20) as response:
    matches = json.load(response)
assert any('fixture.txt' in m['path']['text'] for m in matches), matches
for endpoint in ['/session/status', '/config', '/mcp']:
    with urllib.request.urlopen('http://127.0.0.1:4096' + endpoint, timeout=10) as response:
        assert response.status == 200
request = urllib.request.Request('http://127.0.0.1:4096/session', data=b'{}', headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request, timeout=10) as response:
    assert json.load(response)['id'].startswith('ses_')
time.sleep(30)
assert not Path('/state/opencode/home/.npm').exists(), 'unexpected background npm install'
assert not any(Path('/state/opencode').rglob('node_modules'))
print('offline-native-search-passed')
'''


def main():
    with closing(docker.from_env()) as client, tempfile.TemporaryDirectory(prefix='cloud-search-') as tmp:
        root = Path(tmp)
        for name in ['workspace', 'state']:
            (root / name).mkdir(mode=0o777)
            (root / name).chmod(0o777)
        (root / 'workspace/fixture.txt').write_text('OFFLINE_SEARCH_MARKER\n')
        container = client.containers.run(
            os.environ.get('RUNTIME_IMAGE', 'cloud-agent-runtime:dev'), detach=True, network_mode='none',
            init=True, environment={'XDG_CONFIG_HOME': '/opt/agent/global'},
            read_only=True, tmpfs={'/tmp': 'rw,nosuid,size=512m'},
            labels={'cloud.verification': 'runtime-search'},
            volumes={str(root / 'workspace'): {'bind': '/workspace', 'mode': 'rw'}, str(root / 'state'): {'bind': '/state/opencode', 'mode': 'rw'},
                     str(ROOT / 'agents/agent-code'): {'bind': '/opt/agent', 'mode': 'ro'}},
        )
        report = {'result': 'failed', 'image_id': container.image.id}
        try:
            result = container.exec_run(['python3', '-c', PROBE])
            assert result.exit_code == 0, result.output.decode(errors='replace')
            report.update(result='passed', network='none', observation_seconds=30,
                          check='native search, session creation/status, config and MCP work offline; no npm cache/node_modules after project initialization')
        finally:
            container.remove(force=True)
            destination = ROOT / 'artifacts/runtime-image/search-report.json'
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report))


if __name__ == '__main__':
    main()
