#!/usr/bin/env bash
set -euo pipefail

: "${NODE_VERSION:?NODE_VERSION is not set}"
: "${OPENCODE_VERSION:?OPENCODE_VERSION is not set}"

test "$(id -u)" = 10001
test "$(node --version)" = "v${NODE_VERSION}"
test "$(opencode --version)" = "${OPENCODE_VERSION}"
test "$(python3 --version)" = "Python ${PYTHON_VERSION:?PYTHON_VERSION is not set}"
git --version
rg --version
curl --version >/dev/null
jq --version

python3 - <<'PY'
import docx
import httpx
import lxml
import matplotlib
import numpy
import openpyxl
import pandas
import PIL
import pptx
import requests
import xlsxwriter
import yaml

print("python-imports-ok")
PY

for variable in \
    OPENCODE_DISABLE_AUTOUPDATE \
    OPENCODE_DISABLE_MODELS_FETCH \
    OPENCODE_DISABLE_DEFAULT_PLUGINS \
    OPENCODE_DISABLE_LSP_DOWNLOAD
do
    test "${!variable:-}" = 1
done

for directory in /workspace /state/opencode /tmp
do
    probe=$(mktemp "${directory%/}/image-smoke.XXXXXX")
    printf 'ok\n' >"$probe"
    test "$(cat "$probe")" = ok
    rm -f "$probe"
done

echo "runtime-image-smoke-ok"
