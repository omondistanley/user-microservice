-- Expense microservice schema and tables.
-- Schema name used as "database" in app (expenses_db).
-- Run: python run_migration.py migrations/001_schema.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS expenses_db;

-- Category master: code + name (words and numbers)
CREATE TABLE IF NOT EXISTS expenses_db.category (
    category_code SMALLINT PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE
);

-- Seed categories (idempotent: insert only if not exists)
INSERT INTO expenses_db.category (category_code, name) VALUES
    (1, 'Food'),
    (2, 'Transportation'),
    (3, 'Travel'),
    (4, 'Utilities'),
    (5, 'Entertainment'),
    (6, 'Health'),
    (7, 'Shopping'),
    (8, 'Other')
ON CONFLICT (category_code) DO NOTHING;

-- Expense table
CREATE TABLE IF NOT EXISTS expenses_db.expense (
    expense_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    category_code SMALLINT NOT NULL,
    category_name VARCHAR(64) NOT NULL,
    amount NUMERIC(19, 4) NOT NULL CHECK (amount >= 0),
    date DATE NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    budget_category_id VARCHAR(64) NULL,
    description VARCHAR(2000) NULL,
    balance_after NUMERIC(19, 4) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_expense_user_date ON expenses_db.expense (user_id, date);
CREATE INDEX IF NOT EXISTS idx_expense_user_category ON expenses_db.expense (user_id, category_code);
CREATE INDEX IF NOT EXISTS idx_expense_user_created ON expenses_db.expense (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_expense_user_date_created_id ON expenses_db.expense (user_id, date, created_at, expense_id);
CREATE INDEX IF NOT EXISTS idx_expense_user_deleted ON expenses_db.expense (user_id) WHERE deleted_at IS NULL;

-- Receipt table (metadata only, files in object storage)
CREATE TABLE IF NOT EXISTS expenses_db.receipt (
    receipt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    expense_id UUID NOT NULL,
    user_id INTEGER NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(128) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    storage_key VARCHAR(512) NOT NULL UNIQUE,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE expenses_db.receipt DROP CONSTRAINT IF EXISTS fk_receipt_expense;
ALTER TABLE expenses_db.receipt ADD CONSTRAINT fk_receipt_expense
    FOREIGN KEY (expense_id) REFERENCES expenses_db.expense(expense_id);

CREATE INDEX IF NOT EXISTS idx_receipt_expense ON expenses_db.receipt (expense_id);
CREATE INDEX IF NOT EXISTS idx_receipt_user ON expenses_db.receipt (user_id);
