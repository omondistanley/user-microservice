#!/usr/bin/env bash
# Fail if any *.sql under a service migrations dir is not referenced in deploy/release.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REL="$ROOT/deploy/release.sh"
fail=0

check_service() {
  local dir="$1"
  local label="$2"
  while IFS= read -r -d '' f; do
    base=$(basename "$f")
    if ! grep -qF "$base" "$REL"; then
      echo "ERROR: $label migration $base is missing from deploy/release.sh"
      fail=1
    fi
  done < <(find "$dir" -maxdepth 1 -name '*.sql' -print0 | sort -z)
}

check_service "$ROOT/expense-microservice/migrations" "expense"
check_service "$ROOT/investments-microservice/migrations" "investment"
# User: tracked migrations only (numeric + create_user_table.sql; skip legacy one-offs)
while IFS= read -r -d '' f; do
  base=$(basename "$f")
  if ! grep -qF "$base" "$REL"; then
    echo "ERROR: user migration $base is missing from deploy/release.sh"
    fail=1
  fi
done < <(find "$ROOT/user-microservice/migrations" -maxdepth 1 \( -name 'create_user_table.sql' -o -name '[0-9][0-9][0-9]_*.sql' \) -print0 | sort -z)

while IFS= read -r -d '' f; do
  base=$(basename "$f")
  if ! grep -qF "$base" "$REL"; then
    echo "ERROR: budget migration $base is missing from deploy/release.sh"
    fail=1
  fi
done < <(find "$ROOT/budget-microservice/migrations" -maxdepth 1 -name '*.sql' -print0 | sort -z)

if [ "$fail" -ne 0 ]; then
  exit 1
fi
echo "OK: all migration files are listed in deploy/release.sh"
