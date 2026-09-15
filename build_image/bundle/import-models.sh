#!/bin/sh
# Run beside compose.json/tooling/config; default is dry-run, never publishes.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ -f "$ROOT/tooling/config/tooling/seed.py" ] || { echo 'Run this script from a complete extracted release, not artifacts/scripts/server alone.' >&2; exit 1; }
SEED=models.example.json
[ ! -f "$ROOT/config/catalog_service/seeds/models.default.json" ] || SEED=models.default.json
if [ "$#" -gt 0 ]; then
  case "$1" in -*) ;; *) SEED=$1; shift;; esac
fi
if [ -f "$ROOT/config/catalog_service/.env" ]; then
  set -- --env-file "$ROOT/config/catalog_service/.env" "$@"
elif [ -f "$ROOT/.env" ]; then
  set -- --env-file "$ROOT/.env" "$@"
fi
export PYTHONPATH="$ROOT/tooling"
exec "${SEED_PYTHON:-python3}" -m config.tooling seed-import "$SEED" \
  --config-root "$ROOT/config" --catalog-url "${API_BASE_URL:-http://127.0.0.1:18080}" \
  --token-env ADMIN_TOKEN "$@"
