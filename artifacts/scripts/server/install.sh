#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || { echo 'Supported host: Linux amd64' >&2; exit 1; }
[ -f SHA256SUMS ] || { echo 'Incomplete release: SHA256SUMS missing (prepare-only is not installable)' >&2; exit 1; }
sha256sum -c SHA256SUMS
if ! command -v docker >/dev/null 2>&1; then ./install-docker.sh; fi
docker info >/dev/null
docker compose version >/dev/null
if [ ! -f .env ]; then
  umask 077
  TOKEN=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
  ADMIN=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
  MODEL=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
  printf 'SERVICE_TOKEN=%s\nADMIN_TOKEN=%s\nMODEL_GATEWAY_TOKEN=%s\nDEPLOY_ROOT=%s\nCOMPOSE_PROJECT_NAME=opencode_cloud\n' "$TOKEN" "$ADMIN" "$MODEL" "$ROOT" > .env
fi
if ! grep -q '^DOCKER_BRIDGE_IP=.' .env; then
  BRIDGE_IP=$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')
  [ -n "$BRIDGE_IP" ] || { echo 'Docker default bridge gateway unavailable' >&2; exit 1; }
  printf '\nDOCKER_BRIDGE_IP=%s\n' "$BRIDGE_IP" >> .env
fi
mkdir -p data/workspaces log
for archive in images/*.tar; do docker load -i "$archive"; done
./compose.sh config --quiet
./compose.sh up -d --wait
echo 'Installed. Administrator token is stored in .env.'
