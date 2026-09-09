#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
export MODEL_GATEWAY_BRIDGE_IP
MODEL_GATEWAY_BRIDGE_IP=$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')
test -n "$MODEL_GATEWAY_BRIDGE_IP"
exec docker compose --env-file "${MODEL_GATEWAY_ENV_FILE:-$project_dir/deploy/.env}" \
  -f "$project_dir/deploy/docker-compose.yml" "$@"
