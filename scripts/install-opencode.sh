#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
. "$project_dir/versions.env"
test "$(node --version)" = "v$NODE_VERSION"
npm install --global --prefix /usr/local "opencode-ai@$OPENCODE_VERSION"
test "$(opencode --version)" = "$OPENCODE_VERSION"
which opencode
