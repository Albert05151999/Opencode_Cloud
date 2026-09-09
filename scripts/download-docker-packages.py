"""Download pinned official Docker debs; supports Windows as a WSL download bridge."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
out = root / 'artifacts/env/docker-download'
out.mkdir(parents=True, exist_ok=True)
base = 'https://download.docker.com/linux/ubuntu/'
curl = shutil.which('curl.exe') or shutil.which('curl')
def fetch(url, path):
    subprocess.run([curl, '-fsSL', '--retry', '3', '--retry-all-errors', '--max-time', '180', url, '-o', str(path)], check=True)

for remote, local in [('gpg', 'docker.asc'), ('dists/noble/InRelease', 'InRelease'), ('dists/noble/stable/binary-amd64/Packages.gz', 'Packages.gz')]:
    fetch(base + remote, out / local)
release = (out / 'InRelease').read_text(encoding='utf-8')
expected = re.search(r'^\s+([0-9a-f]{64})\s+\d+\s+stable/binary-amd64/Packages.gz$', release, re.M).group(1)
assert hashlib.sha256((out / 'Packages.gz').read_bytes()).hexdigest() == expected
packages = gzip.decompress((out / 'Packages.gz').read_bytes()).decode()
rows = [dict(line.split(': ', 1) for line in block.splitlines() if ': ' in line and not line.startswith(' ')) for block in packages.split('\n\n')]
pins = {
    'docker-ce': '5:29.8.0-1~ubuntu.24.04~noble',
    'docker-ce-cli': '5:29.8.0-1~ubuntu.24.04~noble',
    'containerd.io': '2.3.4-2~ubuntu.24.04~noble',
    'docker-buildx-plugin': '0.37.0-1~ubuntu.24.04~noble',
    'docker-compose-plugin': '5.5.1-1~ubuntu.24.04~noble',
}
manifest = []
for name, version in pins.items():
    row = next(r for r in rows if r.get('Package') == name and r['Version'] == version)
    remote = row['Filename']
    assert remote.startswith('dists/noble/pool/stable/amd64/') and '..' not in remote
    path = out / Path(remote).name
    fetch(base + remote, path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row['SHA256']
    manifest.append({'package': name, 'version': version, 'file': path.name, 'sha256': row['SHA256']})
    print(name, version, 'SHA256 passed', flush=True)
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print('Before installation, verify InRelease with scripts/verify-docker-repository.sh.')
