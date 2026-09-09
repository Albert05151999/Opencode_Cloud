#!/usr/bin/env bash
set -euo pipefail
# Run with: wsl -d Ubuntu-24.04 -u root -- bash /mnt/e/Project_Space/Opencode_Cloud/scripts/setup-ubuntu.sh
test "$(id -u)" = 0
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
export DEBIAN_FRONTEND=noninteractive
apt-get -o APT::Update::Error-Mode=any update
apt-get upgrade -y
apt-get install -y ca-certificates curl wget git jq unzip zip zstd \
  build-essential pkg-config make gcc g++ python3 python3-venv python3-pip \
  sqlite3 strace lsof iproute2 net-tools
git --version
curl --version
python3 --version
sqlite3 --version
strace -V
