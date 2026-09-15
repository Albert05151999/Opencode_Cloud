#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/../../.." && pwd)
NODE_VERSION=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["NODE_VERSION"])' "$project_dir/config/build_image/versions.json")
OPENCODE_VERSION=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["OPENCODE_VERSION"])' "$project_dir/config/build_image/versions.json")
image=${RUNTIME_IMAGE:-opencode-cloud/agent_runtime:1.0.0}
run_id="runtime-verify-$$"
normal_name="${run_id}-normal"
readonly_name="${run_id}-readonly"
test_root=$(mktemp -d -p /tmp cloud-agent-runtime-test.XXXXXX)
cleanup() {
  docker rm -f "$normal_name" "$readonly_name" >/dev/null 2>&1 || true
  case "$test_root" in
    /tmp/cloud-agent-runtime-test.*)
      if test -d "$test_root"; then
        docker run --rm --user 0 --entrypoint chmod \
          --mount "type=bind,src=$test_root,dst=/cleanup" "$image" -R a+rwX /cleanup >/dev/null 2>&1 || true
        rm -rf -- "$test_root"
      fi
      ;;
  esac
}
trap cleanup EXIT
mkdir -p "$test_root/workspace" "$test_root/state" "$test_root/log" "$test_root/agent/global/opencode"
touch "$test_root/agent/global/opencode/.gitignore"
cp "$project_dir/agent_runtime/image/opencode/global/opencode.json" "$test_root/agent/opencode.json"
chmod -R a+rwX "$test_root/workspace" "$test_root/state" "$test_root/log"
chmod -R a+rX "$test_root/agent"
if [[ ${SKIP_BUILD:-0} != 1 ]]; then
  python3 "$project_dir/build_image/build.py" module agent_runtime --profile production
fi
test "$(docker image inspect "$image" --format '{{.Config.User}}')" = agent:agent
docker run -d --init --name "$normal_name" -p 127.0.0.1::4096 \
  --mount "type=bind,src=$test_root/log,dst=/runtime-log" \
  --mount "type=bind,src=$test_root/workspace,dst=/workspace" \
  --mount "type=bind,src=$test_root/state,dst=/state/opencode" \
  --mount "type=bind,src=$test_root/agent,dst=/opt/agent,readonly" "$image" >/dev/null
port=$(docker port "$normal_name" 4096/tcp | awk -F: 'NR==1 {print $NF}')
for attempt in $(seq 1 100); do
  if health=$(curl --noproxy 127.0.0.1 --connect-timeout 1 --max-time 2 -fsS "http://127.0.0.1:$port/global/health" 2>/dev/null); then break; fi
  test "$attempt" -lt 100 || { docker logs "$normal_name"; exit 1; }
  sleep 0.1
done
python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert d == {"healthy": True, "version": sys.argv[2]}' "$health" "$OPENCODE_VERSION"
docker run --rm --entrypoint /opt/runtime/image-smoke.sh \
  --mount "type=bind,src=$test_root/workspace,dst=/workspace" \
  --mount "type=bind,src=$test_root/state,dst=/state/opencode" "$image"
docker rm -f "$normal_name" >/dev/null
docker run -d --init --name "$readonly_name" --read-only --tmpfs /tmp:rw,nosuid,size=512m \
  --mount "type=bind,src=$test_root/log,dst=/runtime-log" \
  -p 127.0.0.1::4096 \
  --mount "type=bind,src=$test_root/workspace,dst=/workspace" \
  --mount "type=bind,src=$test_root/state,dst=/state/opencode" \
  --mount "type=bind,src=$test_root/agent,dst=/opt/agent,readonly" "$image" >/dev/null
port=$(docker port "$readonly_name" 4096/tcp | awk -F: 'NR==1 {print $NF}')
for attempt in $(seq 1 100); do
  curl --noproxy 127.0.0.1 --connect-timeout 1 --max-time 2 -fsS "http://127.0.0.1:$port/global/health" >/dev/null 2>&1 && break
  test "$attempt" -lt 100 || { docker logs "$readonly_name"; exit 1; }
  sleep 0.1
done
test "$(docker inspect "$readonly_name" --format '{{.HostConfig.ReadonlyRootfs}}')" = true
test "$(docker exec "$readonly_name" id -u)" = 10001
docker exec "$readonly_name" sh -c 'printf workspace > /workspace/persist.txt; printf state > /state/opencode/persist.txt; printf tmp > /tmp/ephemeral.txt'
if docker exec "$readonly_name" sh -c 'touch /opt/agent/forbidden'; then exit 1; fi
if docker exec "$readonly_name" sh -c 'touch /usr/local/forbidden'; then exit 1; fi
docker restart "$readonly_name" >/dev/null
for attempt in $(seq 1 100); do
  port=$(docker port "$readonly_name" 4096/tcp | awk -F: 'NR==1 {print $NF}')
  curl --noproxy 127.0.0.1 --connect-timeout 1 --max-time 2 -fsS "http://127.0.0.1:$port/global/health" >/dev/null 2>&1 && break
  test "$attempt" -lt 100 || { docker logs "$readonly_name"; exit 1; }
  sleep 0.1
done
test "$(cat "$test_root/workspace/persist.txt")" = workspace
test "$(cat "$test_root/state/persist.txt")" = state
mkdir -p "$project_dir/artifacts/runtime-image"
image_id=$(docker image inspect "$image" --format '{{.Id}}')
image_size=$(docker image inspect "$image" --format '{{.Size}}')
python3 - "$project_dir/artifacts/runtime-image/report.json" "$image_id" "$image_size" "$NODE_VERSION" "$OPENCODE_VERSION" <<'PY'
import json, sys
from pathlib import Path
report = {'result': 'passed', 'image_id': sys.argv[2], 'image_size_bytes': int(sys.argv[3]),
          'node_version': sys.argv[4], 'opencode_version': sys.argv[5],
          'checks': ['normal health', 'image smoke', 'non-root uid 10001', 'read-only rootfs health',
                     'workspace/state/tmp writable', 'agent/system paths not writable', 'restart persistence']}
Path(sys.argv[1]).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
PY
