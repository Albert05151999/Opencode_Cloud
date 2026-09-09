#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
. "$project_dir/versions.env"
test "$(node --version)" = "v$NODE_VERSION"
test "$(command -v node)" = /usr/local/bin/node
test "$(command -v npm)" = /usr/local/bin/npm
node --version
npm --version
which node
which npm
node -e 'if (process.platform !== "linux" || !process.version.startsWith("v24.")) process.exit(1); console.log("node-ok", process.version, process.platform)'
