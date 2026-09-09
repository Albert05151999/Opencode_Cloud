#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" = 0
project_dir=$(cd "$(dirname "$0")/.." && pwd)
bash "$project_dir/scripts/verify-docker-repository.sh"
test ! -S /var/run/docker.sock || { echo 'Existing daemon detected; inspect first'; exit 1; }
cd "$project_dir/artifacts/env/docker-download"
python3 - <<'PY'
import hashlib, json
from pathlib import Path
for item in json.loads(Path('manifest.json').read_text()):
    assert hashlib.sha256(Path(item['file']).read_bytes()).hexdigest() == item['sha256']
PY
apt-get -o APT::Update::Error-Mode=any update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ./*.deb
systemctl enable --now docker
usermod -aG docker zephyrusg14
dpkg-query -W docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin > "$project_dir/artifacts/env/docker-packages.txt"
