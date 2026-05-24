#!/usr/bin/env bash
# Build Eve runtime Docker images.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "$#" -eq 0 ]; then
  variant="all"
else
  variant="$1"
fi

build_slim() {
  docker build \
    -f docker/Dockerfile \
    --target runtime-slim \
    -t eve/eve:slim \
    -t eve/eve:latest \
    .
}

build_full() {
  docker build \
    -f docker/Dockerfile \
    --platform linux/amd64 \
    --target runtime-full \
    -t eve/eve:full \
    .
}

case "$variant" in
  all)
    build_slim
    build_full
    ;;
  full)
    build_full
    ;;
  slim)
    build_slim
    ;;
  *)
    echo "Usage: docker/build.sh [all|slim|full]" >&2
    exit 2
    ;;
esac
