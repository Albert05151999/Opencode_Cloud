#!/usr/bin/env bash
set -euo pipefail
export OPENCODE_DISABLE_AUTOUPDATE=1
export OPENCODE_DISABLE_MODELS_FETCH=1
export OPENCODE_DISABLE_DEFAULT_PLUGINS=1
export OPENCODE_DISABLE_LSP_DOWNLOAD=1
export OPENCODE_CONFIG="${OPENCODE_CONFIG:-/opt/agent/opencode.json}"
export HOME="${OPENCODE_HOME:-/state/opencode/home}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-/state/opencode/data}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/opt/agent/global}"
exec opencode serve --hostname "${OPENCODE_HOSTNAME:-0.0.0.0}" --port "${OPENCODE_PORT:-4096}"
