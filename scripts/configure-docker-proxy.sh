#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" = 0
proxy_url=${1:-}
case "$proxy_url" in
  http://127.0.0.1:[0-9]*) ;;
  *) echo 'Usage: configure-docker-proxy.sh http://127.0.0.1:PORT' >&2; exit 2 ;;
esac
install -d -m 0755 /etc/systemd/system/docker.service.d
escaped=${proxy_url//%/%%}
no_proxy='localhost,127.0.0.1,::1,ghcr.io,.githubusercontent.com'
printf '[Service]\nEnvironment="HTTP_PROXY=%s"\nEnvironment="HTTPS_PROXY=%s"\nEnvironment="NO_PROXY=%s"\n' \
  "$escaped" "$escaped" "$no_proxy" > /etc/systemd/system/docker.service.d/http-proxy.conf
systemctl daemon-reload
systemctl restart docker
systemctl show docker --property=Environment
