#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python_bin=${PYTHON_BIN:-python3.12}
pip_tools_version=7.5.2
controller_lock="$root/requirements-controller.lock"
runtime_lock="$root/runtime/requirements.lock"

update_locks() (
    tool_dir=$(mktemp -d)
    trap 'rm -rf "$tool_dir"' EXIT
    "$python_bin" -m venv "$tool_dir/venv"
    env -u PIP_NO_INDEX PIP_CONFIG_FILE=/dev/null "$tool_dir/venv/bin/python" -m pip install --disable-pip-version-check \
        --index-url=https://pypi.org/simple "pip-tools==$pip_tools_version"
    upgrade=--no-upgrade
    if [[ ${1:-} == --upgrade ]]; then
        upgrade=--upgrade
    elif [[ $# -ne 0 ]]; then
        echo "usage: $0 update [--upgrade]" >&2
        return 2
    fi
    (
        cd "$root"
        env -u PIP_NO_INDEX PIP_CONFIG_FILE=/dev/null \
            CUSTOM_COMPILE_COMMAND="bash scripts/python-dependency-locks.sh update" \
            "$tool_dir/venv/bin/pip-compile" pyproject.toml \
            --generate-hashes --resolver=backtracking --strip-extras "$upgrade" \
            --index-url=https://pypi.org/simple --no-emit-index-url \
            --output-file=requirements-controller.lock
        env -u PIP_NO_INDEX PIP_CONFIG_FILE=/dev/null \
            CUSTOM_COMPILE_COMMAND="bash scripts/python-dependency-locks.sh update" \
            "$tool_dir/venv/bin/pip-compile" runtime/requirements.txt \
            --generate-hashes --resolver=backtracking --strip-extras "$upgrade" \
            --index-url=https://pypi.org/simple --no-emit-index-url \
            --output-file=runtime/requirements.lock
    )
    echo "locks generated with pip-tools $pip_tools_version and $($python_bin --version 2>&1)"
)

verify_lock() {
    name=$1
    lock=$2
    environment=$3
    "$python_bin" -m venv "$environment"
    env -u PIP_NO_INDEX PIP_CONFIG_FILE=/dev/null "$environment/bin/python" -m pip install --disable-pip-version-check \
        --index-url=https://pypi.org/simple \
        --require-hashes --only-binary=:all: --requirement "$lock"
    "$environment/bin/python" -m pip check
    echo "$name lock verified with --require-hashes"
}

verify_locks() (
    verify_dir=$(mktemp -d)
    trap 'rm -rf "$verify_dir"' EXIT
    verify_lock controller "$controller_lock" "$verify_dir/controller"
    verify_lock runtime "$runtime_lock" "$verify_dir/runtime"
    echo "both locks verified with $($python_bin --version 2>&1)"
)

case ${1:-} in
    update)
        shift
        update_locks "$@"
        ;;
    verify)
        shift
        [[ $# -eq 0 ]] || { echo "usage: $0 verify" >&2; exit 2; }
        verify_locks
        ;;
    *)
        echo "usage: $0 {update [--upgrade]|verify}" >&2
        exit 2
        ;;
esac
