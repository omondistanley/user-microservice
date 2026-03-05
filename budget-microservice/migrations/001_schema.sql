-- Budget microservice schema and tables.
-- Schema name used as "database" in app (budgets_db).
-- Run: python run_migration.py migrations/001_schema.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS budgets_db;

-- Budget table: per-user, per-category, with date range for history
CREATE TABLE IF NOT EXISTS budgets_db.budget (
    budget_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    name VARCHAR(255) NULL,
    category_code SMALLINT NOT NULL,
    amount NUMERIC(19, 4) NOT NULL CHECK (amount >= 0),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_budget_dates CHECK (start_date <= end_date)
);

CREATE INDEX IF NOT EXISTS idx_budget_user_dates ON budgets_db.budget (user_id, start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_budget_user_category ON budgets_db.budget (user_id, category_code);
