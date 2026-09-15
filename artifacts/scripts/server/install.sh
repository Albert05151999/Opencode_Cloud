#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || { echo 'Supported host: Linux amd64' >&2; exit 1; }
[ -f SHA256SUMS ] || { echo 'Incomplete release: SHA256SUMS missing (prepare-only is not installable)' >&2; exit 1; }
sha256sum -c SHA256SUMS
chmod 755 "$ROOT"/*.sh
if ! command -v docker >/dev/null 2>&1; then ./install-docker.sh; fi
docker info >/dev/null
docker compose version >/dev/null
command -v python3 >/dev/null 2>&1 || { echo 'Install Python 3 on the host before running install.sh.' >&2; exit 1; }
umask 077
PYTHONPATH="$ROOT/tooling" python3 -m config.tooling.deployment_env --env-file "$ROOT/.env" --deploy-root "$ROOT"
if ! grep -q '^DOCKER_BRIDGE_IP=.' .env; then
  BRIDGE_IP=$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')
  [ -n "$BRIDGE_IP" ] || { echo 'Docker default bridge gateway unavailable' >&2; exit 1; }
  printf '\nDOCKER_BRIDGE_IP=%s\n' "$BRIDGE_IP" >> .env
fi
mkdir -p data/workspaces log
./compose.sh config --quiet
PYTHONPATH="$ROOT/tooling" python3 -m config.tooling.deployment_check --root "$ROOT" --phase pre
for archive in images/*.tar; do docker load -i "$archive"; done
./compose.sh up -d --wait
PYTHONPATH="$ROOT/tooling" python3 -m config.tooling.deployment_check --root "$ROOT" --phase post
PYTHONPATH="$ROOT/tooling" python3 -m config.tooling.bootstrap --root "$ROOT"
echo 'Installed. Administrator token is stored in .env.'
