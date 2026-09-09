#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" = 0
project_dir=$(cd "$(dirname "$0")/.." && pwd)
. "$project_dir/versions.env"
test "$(uname -m)" = x86_64
archive="node-v${NODE_VERSION}-linux-x64.tar.xz"
cache_dir="$project_dir/artifacts/env/node-download"
mkdir -p "$cache_dir"
cd "$cache_dir"
curl --fail --location --retry 3 --max-time 180 "https://nodejs.org/dist/v${NODE_VERSION}/${archive}" -o "$archive"
curl --fail --location --retry 3 --max-time 30 "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" -o SHASUMS256.txt
grep "  ${archive}$" SHASUMS256.txt | sha256sum --check -
printf '%s  %s\n' "$NODE_ARCHIVE_SHA256" "$archive" | sha256sum --check -
tar -xJf "$archive" -C /opt
for executable in node npm npx; do
  ln -sfn "/opt/node-v${NODE_VERSION}-linux-x64/bin/$executable" "/usr/local/bin/$executable"
done
node --version
npm --version
