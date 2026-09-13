#!/bin/sh
# Usage: upgrade-module.sh module image-tag image.tar
# Keep the previous image tag/archive for rollback with the same command.
set -eu
[ "$#" -eq 3 ] || { echo 'usage: upgrade-module.sh module image-tag archive' >&2; exit 2; }
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
case "$1" in api_gateway|catalog_service|sandbox_manager|file_service|model_gateway|operations|observability|nginx|agent_runtime) ;; *) echo 'Unknown service' >&2; exit 2;; esac
case "$2" in *[!a-zA-Z0-9_./:@-]*|'') echo 'Invalid image tag' >&2; exit 2;; esac
docker load -i "$3"
# Loading an unrelated archive must never persist an unusable override.
docker image inspect "$2" >/dev/null
TEMP=$(mktemp "$ROOT/.image-override.XXXXXX")
trap 'rm -f "$TEMP"' EXIT HUP INT TERM
if [ "$1" = agent_runtime ]; then
  printf '{"services":{"catalog_service":{"environment":{"AGENT_RUNTIME_IMAGE":"%s"}},"sandbox_manager":{"environment":{"AGENT_RUNTIME_IMAGE":"%s"}}}}\n' "$2" "$2" > "$TEMP"
  mv "$TEMP" image-override-agent_runtime.json
  ./compose.sh up -d --no-deps --wait catalog_service sandbox_manager
  echo 'Runtime image selected for future Agent versions. Existing sandboxes are not forcibly stopped; publish the affected Agents through operations to adopt it.'
else
  printf '{"services":{"%s":{"image":"%s"}}}\n' "$1" "$2" > "$TEMP"
  mv "$TEMP" "image-override-$1.json"
  ./compose.sh up -d --no-deps --wait "$1"
fi
