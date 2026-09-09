#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd "$(dirname "$0")/.." && pwd)
docker version
docker info
docker run --rm hello-world
docker info --format '{{.DefaultRuntime}}' | grep -Fx runc
docker image inspect hello-world:latest --format '{{.Id}} {{.Architecture}} {{.Os}}'
groups | grep -w docker
{
  docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'
  docker info --format 'runtime={{.DefaultRuntime}} cgroup={{.CgroupVersion}} storage={{.Driver}}'
  docker image inspect hello-world:latest --format 'image={{.Id}} arch={{.Architecture}} os={{.Os}}'
  groups
} > "$project_dir/artifacts/env/docker-verification.txt"
