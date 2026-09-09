#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
python_bin=${CONTROLLER_PYTHON:-/home/zephyrusg14/projects/cloud-agent/.venv-controller/bin/python}
port=${CONTROLLER_TEST_PORT:-18080}
if ss -ltn | awk '{print $4}' | grep -Eq ":${port}$"; then
  echo "Test port $port is already in use" >&2
  exit 1
fi
cd "$project_dir"
"$python_bin" -m pytest
"$python_bin" -m app.main --host 127.0.0.1 --port "$port" > artifacts/env/controller-server.log 2>&1 &
server_pid=$!
cleanup() {
  kill "$server_pid" >/dev/null 2>&1 || true
  wait "$server_pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT
for attempt in $(seq 1 50); do
  if curl --noproxy 127.0.0.1 --connect-timeout 1 --max-time 2 -fsS \
      "http://127.0.0.1:${port}/cloud/health" -o artifacts/env/controller-health.json; then
    break
  fi
  kill -0 "$server_pid"
  test "$attempt" -lt 50 || exit 1
  sleep 0.1
done
"$python_bin" -c 'import json; from pathlib import Path; assert json.loads(Path("artifacts/env/controller-health.json").read_text()) == {"ok": True}'
echo controller-skeleton-ok
