#!/usr/bin/env bash
# Run in Linux / WSL with a local Docker engine and Node.js 24+.
set -euo pipefail
project_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$project_root"
for command in python3.12 docker zstd npm; do
  command -v "$command" >/dev/null || { echo "Missing prerequisite: $command" >&2; exit 1; }
done
docker info >/dev/null
python3.12 -m venv .venv-build
.venv-build/bin/python -m pip install -e '.[test]'
(cd web && npm ci && npm run build)
.venv-build/bin/python -m pytest tests/unit -q
.venv-build/bin/python scripts/build-release-images.py
# A separate output can be supplied without overwriting existing delivery ZIPs.
.venv-build/bin/python scripts/package-web-release.py "$@"
