#!/bin/bash
set -e
# Run all backends on localhost; gateway proxies to them. Gateway runs in foreground so the container stays up.
# DB_HOST, DB_PORT, DB_USER, DB_PASSWORD are set by Fly secrets; we set DB_NAME per process.

# Fly runs release_command as: start.sh /opt/release.sh. Run migrations only and exit.
if [ "$1" = "/opt/release.sh" ]; then
  exec /opt/release.sh
fi

# User service (port 8000) - serves frontend and auth
(export DB_NAME="${DB_NAME:-users_db}"; cd /opt/expense_tracker/user-microservice && exec uvicorn app.main:app --host 0.0.0.0 --port 8000) &

# Expense (3001), Budget (3002), Investment (3003)
(export DB_NAME="expenses_db"; cd /opt/expense && exec uvicorn app.main:app --host 0.0.0.0 --port 3001) &
(export DB_NAME="budgets_db"; cd /opt/budget && exec uvicorn app.main:app --host 0.0.0.0 --port 3002) &
(export DB_NAME="investments_db"; cd /opt/investment && exec uvicorn app.main:app --host 0.0.0.0 --port 3003) &

# Give backends time to bind
sleep 3

# Gateway (8080) - foreground; receives all public traffic and proxies to backends
cd /opt/gateway && exec uvicorn app.main:app --host 0.0.0.0 --port 8080
