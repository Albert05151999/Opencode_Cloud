#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" = 0
project_dir=$(cd "$(dirname "$0")/.." && pwd)
. /etc/os-release
test "$ID" = ubuntu
test "$VERSION_ID" = 24.04
test ! -S /var/run/docker.sock || { echo 'Existing daemon detected; inspect before installing'; exit 1; }
install -m 0755 -d /etc/apt/keyrings
curl -fsSL --retry 3 --max-time 60 https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get -o APT::Update::Error-Mode=any update
docker_version=$(apt-cache madison docker-ce | awk 'NR==1 {print $3}')
test -n "$docker_version"
DEBIAN_FRONTEND=noninteractive apt-get install -y "docker-ce=$docker_version" "docker-ce-cli=$docker_version" containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
usermod -aG docker zephyrusg14
dpkg-query -W docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin > "$project_dir/artifacts/env/docker-packages.txt"
