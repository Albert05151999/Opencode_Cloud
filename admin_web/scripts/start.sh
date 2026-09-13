#!/usr/bin/env sh
set -eu
ADMIN_WEB_ROOT=${ADMIN_WEB_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)}
WEB_PYTHON=${ADMIN_WEB_PYTHON:-$ADMIN_WEB_ROOT/.venv-web/bin/python}
if [ ! -x "$WEB_PYTHON" ]; then
  echo "Admin Web environment is missing; run admin_web/scripts/install.sh first." >&2
  exit 1
fi
cd "$ADMIN_WEB_ROOT"
exec "$WEB_PYTHON" -m admin_web.local_service
