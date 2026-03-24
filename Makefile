# pocketii — top-level Makefile
# Usage:
#   make up          — start all services via docker-compose
#   make down        — stop all services
#   make migrate     — run all migrations for expense and investments DBs
#   make test        — run all tests
#   make lint        — run ruff linter across both microservices
#   make build       — build Docker images
#   make frontend-css — compile Tailwind to frontend/static/css/app.tw.css (requires npm)

COMPOSE := docker compose
EXPENSE_DIR := expense-microservice
INVEST_DIR  := investments-microservice
FRONTEND_DIR := frontend

# ── Frontend (Tailwind) ────────────────────────────────────────────────────────

.PHONY: frontend-css
frontend-css:
	@echo "▶ Building Tailwind CSS..."
	cd $(FRONTEND_DIR) && npm ci && npm run build:css
	@echo "✔ app.tw.css updated."

# ── Docker ────────────────────────────────────────────────────────────────────

.PHONY: up
up:
	$(COMPOSE) up -d

.PHONY: down
down:
	$(COMPOSE) down

.PHONY: build
build:
	$(COMPOSE) build

.PHONY: logs
logs:
	$(COMPOSE) logs -f

# ── Migrations ────────────────────────────────────────────────────────────────
# Applies all *.sql files in order using psql. Reads DB config from .env.

-include .env
export

EXPENSE_DSN ?= postgresql://$(DB_USER):$(DB_PASSWORD)@$(DB_HOST):$(DB_PORT)/$(DB_NAME)
INVEST_DSN  ?= postgresql://$(DB_USER):$(DB_PASSWORD)@$(DB_HOST):$(DB_PORT)/investments_db

.PHONY: migrate
migrate: migrate-expense migrate-invest

.PHONY: migrate-expense
migrate-expense:
	@echo "▶ Applying expense migrations..."
	@for f in $(EXPENSE_DIR)/migrations/*.sql; do \
		echo "  $$f"; \
		psql "$(EXPENSE_DSN)" -f "$$f" --on-error-stop; \
	done
	@echo "✔ Expense migrations done."

.PHONY: migrate-invest
migrate-invest:
	@echo "▶ Applying investments migrations..."
	@for f in $(INVEST_DIR)/migrations/*.sql; do \
		echo "  $$f"; \
		psql "$(INVEST_DSN)" -f "$$f" --on-error-stop; \
	done
	@echo "✔ Investments migrations done."

# ── Tests ─────────────────────────────────────────────────────────────────────

.PHONY: test
test: test-expense test-invest

.PHONY: test-expense
test-expense:
	@echo "▶ Running expense tests..."
	cd $(EXPENSE_DIR) && python -m pytest tests/ -v --tb=short

.PHONY: test-invest
test-invest:
	@echo "▶ Running investments tests..."
	cd $(INVEST_DIR) && python -m pytest tests/ -v --tb=short

# ── Lint ──────────────────────────────────────────────────────────────────────

.PHONY: lint
lint:
	@echo "▶ Linting expense-microservice..."
	cd $(EXPENSE_DIR) && python -m ruff check app/ tests/ --fix
	@echo "▶ Linting investments-microservice..."
	cd $(INVEST_DIR) && python -m ruff check app/ tests/ --fix
	@echo "✔ Lint done."

# ── Helpers ───────────────────────────────────────────────────────────────────

.PHONY: shell-expense
shell-expense:
	$(COMPOSE) exec expense /bin/sh

.PHONY: shell-invest
shell-invest:
	$(COMPOSE) exec investments /bin/sh

.PHONY: psql-expense
psql-expense:
	psql "$(EXPENSE_DSN)"

.PHONY: psql-invest
psql-invest:
	psql "$(INVEST_DSN)"
