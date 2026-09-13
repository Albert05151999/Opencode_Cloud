#!/bin/sh
# Persistent data and credentials are deliberately retained.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
exec ./compose.sh down
