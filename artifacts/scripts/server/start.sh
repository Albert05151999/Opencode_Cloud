#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
PYTHONPATH="$ROOT/tooling" python3 -m config.tooling.deployment_check --root "$ROOT" --phase pre
sh ./compose.sh up -d --wait "$@"
PYTHONPATH="$ROOT/tooling" python3 -m config.tooling.deployment_check --root "$ROOT" --phase post
