#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
venv_dir=${CLOUD_AGENT_VENV:-${HOME}/projects/cloud-agent/.venv}
python3 -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --upgrade pip wheel
if test -f "$project_dir/runtime/requirements.txt"; then
  "$venv_dir/bin/python" -m pip install -r "$project_dir/runtime/requirements.txt"
else
  "$venv_dir/bin/python" -m pip install -r "$project_dir/runtime/requirements.in"
fi
"$venv_dir/bin/python" -m pip check
