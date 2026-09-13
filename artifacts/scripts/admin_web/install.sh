#!/usr/bin/env sh
set -eu
ADMIN_WEB_ROOT=${ADMIN_WEB_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)}
if [ -n "${ADMIN_WEB_PYTHON:-}" ]; then
  WEB_PYTHON=$ADMIN_WEB_PYTHON
else
  WEB_PYTHON="$ADMIN_WEB_ROOT/.venv-web/bin/python"
  if [ ! -x "$WEB_PYTHON" ]; then
    BASE_PYTHON=${PYTHON:-python3}
    if ! "$BASE_PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
      echo "Admin Web requires Python 3.11 or newer; set PYTHON to a compatible interpreter." >&2
      exit 1
    fi
    "$BASE_PYTHON" -m venv "$ADMIN_WEB_ROOT/.venv-web"
  fi
fi
"$WEB_PYTHON" -m pip install -r "$ADMIN_WEB_ROOT/admin_web/local_service/requirements.txt"
