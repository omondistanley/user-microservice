#!/usr/bin/env bash
# Build (and optionally start) with one image at a time to avoid I/O errors.
# Usage:
#   ./scripts/docker-build-serial.sh           # build all serially
#   ./scripts/docker-build-serial.sh up        # build serially then 'docker compose up' (also with limit 1)
#   ./scripts/docker-build-serial.sh service1  # build only service1
set -e
export COMPOSE_PARALLEL_LIMIT=1
cd "$(dirname "$0")/.."

if [[ "${1:-}" == "up" ]]; then
  docker compose build "${@:2}"
  exec docker compose up "${@:2}"
fi

docker compose build "$@"
