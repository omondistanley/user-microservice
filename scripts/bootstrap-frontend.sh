#!/usr/bin/env bash
# Build production static assets for the user-microservice image (frontend/ is COPY'd at build).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
if [[ ! -f package-lock.json ]]; then
  echo "Run npm install in frontend/ first (no package-lock.json)." >&2
  exit 1
fi
npm ci
npm run typecheck
npm run build:js
npm run build:css
echo "OK: frontend/static is ready. Rebuild the user image if using Docker: docker compose build user"
