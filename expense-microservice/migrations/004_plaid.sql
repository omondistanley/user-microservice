-- Plaid linked items and expense source tracking.
-- Run: python run_migration.py migrations/004_plaid.sql

CREATE TABLE IF NOT EXISTS expenses_db.plaid_item (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    item_id VARCHAR(64) NOT NULL UNIQUE,
    access_token_encrypted TEXT NOT NULL,
    institution_id VARCHAR(64) NULL,
    institution_name VARCHAR(255) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plaid_item_user_id ON expenses_db.plaid_item (user_id);

ALTER TABLE expenses_db.expense
    ADD COLUMN IF NOT EXISTS source VARCHAR(16) NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS plaid_transaction_id VARCHAR(64) NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_expense_plaid_transaction_id
    ON expenses_db.expense (plaid_transaction_id) WHERE plaid_transaction_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_expense_user_plaid_tx ON expenses_db.expense (user_id, plaid_transaction_id)
    WHERE plaid_transaction_id IS NOT NULL;
