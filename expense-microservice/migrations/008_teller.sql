-- Teller enrollments and expense source tracking.
-- Run: python run_migration.py migrations/008_teller.sql

CREATE TABLE IF NOT EXISTS expenses_db.teller_enrollment (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    enrollment_id VARCHAR(64) NOT NULL UNIQUE,
    access_token_encrypted TEXT NOT NULL,
    institution_name VARCHAR(255) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_teller_enrollment_user_id ON expenses_db.teller_enrollment (user_id);

-- Track teller as a source on expenses (plaid already added source column in 004)
-- Add teller_transaction_id for dedup
ALTER TABLE expenses_db.expense
    ADD COLUMN IF NOT EXISTS teller_transaction_id VARCHAR(64) NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_expense_teller_transaction_id
    ON expenses_db.expense (teller_transaction_id) WHERE teller_transaction_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_expense_user_teller_tx ON expenses_db.expense (user_id, teller_transaction_id)
    WHERE teller_transaction_id IS NOT NULL;
