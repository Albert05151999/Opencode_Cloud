#!/bin/sh
# Offline Docker static binaries + Compose plugin, supplied with release.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || { echo 'Supported host: Linux amd64' >&2; exit 1; }
wait_for_docker() {
  command -v timeout >/dev/null 2>&1 || { echo 'Host needs coreutils timeout for bounded Docker readiness checks.' >&2; return 1; }
  ATTEMPT=0
  while [ "$ATTEMPT" -lt 30 ]; do
    if timeout 1 docker info >/dev/null 2>&1; then return 0; fi
    ATTEMPT=$((ATTEMPT + 1))
    sleep 1
  done
  echo 'Docker daemon did not become ready within 60 seconds, or the current user cannot access its socket.' >&2
  echo 'Inspect locally: systemctl status docker --no-pager; journalctl -u docker --no-pager -n 100' >&2
  return 1
}
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  wait_for_docker
  exit 0
fi
[ "$(id -u)" -eq 0 ] || { echo 'Run Docker host installation as root' >&2; exit 1; }
MISSING=
for requirement in iptables ip6tables ps git xz systemctl tar gzip sha256sum install mktemp mkdir rm awk sleep timeout; do
  if ! command -v "$requirement" >/dev/null 2>&1; then MISSING="$MISSING $requirement"; fi
done
[ -z "$MISSING" ] || {
  echo "Missing host prerequisites:$MISSING" >&2
  echo 'Provision these operating-system packages before offline installation; this script never downloads packages.' >&2
  exit 1
}
[ -d /run/systemd/system ] || { echo 'Host must be booted with systemd before installing the Docker service.' >&2; exit 1; }
[ -r /proc/mounts ] && awk '$3 == "cgroup" || $3 == "cgroup2" { found=1 } END { exit !found }' /proc/mounts || {
  echo 'Host requires a mounted cgroup hierarchy (cgroup v1 or v2).' >&2; exit 1;
}
if [ "${1:-}" = --check-host ]; then echo 'Docker static installer host prerequisites passed.'; exit 0; fi
[ -f "$ROOT/docker/docker.tgz" ] && [ -f "$ROOT/docker/docker-compose" ] && [ -f "$ROOT/docker/SHA256SUMS" ] || {
 echo 'Supply verified Docker amd64 static docker.tgz, docker-compose and SHA256SUMS in docker/, or install Docker Engine + Compose before installation.' >&2; exit 1;
}
(cd "$ROOT/docker" && sha256sum -c SHA256SUMS)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
tar -xzf "$ROOT/docker/docker.tgz" -C "$TMP"
install -m 0755 "$TMP"/docker/* /usr/local/bin/
mkdir -p /usr/local/lib/docker/cli-plugins
install -m 0755 "$ROOT/docker/docker-compose" /usr/local/lib/docker/cli-plugins/docker-compose
cat > /etc/systemd/system/docker.service <<'UNIT'
[Unit]
Description=Docker Engine
After=network-online.target
Wants=network-online.target
[Service]
ExecStart=/usr/local/bin/dockerd
Restart=always
Delegate=yes
KillMode=process
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now docker
wait_for_docker
