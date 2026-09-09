#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
key_dir=$(mktemp -d)
chmod 700 "$key_dir"
gpg --homedir "$key_dir" --import "$project_dir/artifacts/env/docker-download/docker.asc"
gpg --homedir "$key_dir" --verify "$project_dir/artifacts/env/docker-download/InRelease"
