#!/bin/sh
set -e

create_db_if_missing() {
  db_name="$1"
  exists="$(psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${db_name}'")"
  if [ "$exists" != "1" ]; then
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -c "CREATE DATABASE ${db_name};"
  fi
}

create_db_if_missing "users_db"
create_db_if_missing "expenses_db"
create_db_if_missing "budgets_db"
