#!/bin/sh
# Apply persistent per-module image overrides on every operation.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
# Preserve caller arguments while prepending each override.
for override in image-override-*.json; do
  [ -f "$override" ] || continue
  set -- -f "$override" "$@"
done
exec docker compose --env-file .env -f compose.json "$@"
