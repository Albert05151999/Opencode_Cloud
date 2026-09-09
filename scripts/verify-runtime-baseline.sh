#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
venv_dir=${CLOUD_AGENT_VENV:-${HOME}/projects/cloud-agent/.venv}
bash "$project_dir/scripts/verify-node.sh"
python3 "$project_dir/scripts/verify-opencode.py"
python3 "$project_dir/scripts/verify-opencode.py" --stabilized
python3 "$project_dir/scripts/verify-opencode.py" --config-check
"$venv_dir/bin/python" -m pip check
"$venv_dir/bin/python" "$project_dir/scripts/verify-python-runtime.py"
