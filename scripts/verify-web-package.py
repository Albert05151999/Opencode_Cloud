"""Exercise the delivered Windows launcher in a fresh extracted Web package."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('zip', type=Path)
    args = parser.parse_args()
    assert os.name == 'nt', 'Run on Windows'
    work = Path(tempfile.mkdtemp(prefix='cloud-web-package-'))
    with zipfile.ZipFile(args.zip) as archive:
        archive.extractall(work)
    package = next(work.glob('cloud-agent-web-*'))
    env = dict(os.environ, LOCALAPPDATA=str(work / 'local-data'), PYTHONDONTWRITEBYTECODE='1')
    report = {'result': 'running', 'package': args.zip.name, 'checks': []}
    with (work / 'launcher.log').open('w') as log:
        process = subprocess.Popen(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', str(package / 'start-web.ps1'), '-Port', '18768', '-NoBrowser'],
            cwd=package, env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(180):
                if process.poll() is not None:
                    raise RuntimeError('Packaged launcher failed; inspect ' + str(work / 'launcher.log'))
                try:
                    with opener.open('http://127.0.0.1:18768/local/bootstrap', timeout=2) as response:
                        assert json.load(response)['csrf']
                    break
                except OSError:
                    time.sleep(1)
            else:
                raise RuntimeError('Packaged launcher startup timeout')
            with opener.open('http://127.0.0.1:18768/chat') as response:
                assert b'<div id="root">' in response.read()
            python = package / '.venv-web/Scripts/python.exe'
            subprocess.run([str(python), '-c',
                'from pathlib import Path; import local_web.resource_import as m; '
                'assert Path(m.__file__).resolve().is_relative_to(Path.cwd().resolve()); '
                'from app.transfers import parse_native'], cwd=package, env=env, check=True)
            report.update(result='passed', checks=['fresh Windows launcher and dependency install',
                'same-origin bootstrap and compiled chat', 'packaged resource importer dependencies'])
        finally:
            # Only the tree launched above belongs to this verification.
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            process.wait(timeout=15)
            (ROOT / 'artifacts/web/web-package-verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
