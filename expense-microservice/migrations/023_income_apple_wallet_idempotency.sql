-- Apple Wallet webhook income idempotency support.
-- Run: python run_migration.py migrations/023_income_apple_wallet_idempotency.sql

ALTER TABLE expenses_db.income
    ADD COLUMN IF NOT EXISTS apple_wallet_transaction_id VARCHAR(64) NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_income_apple_wallet_transaction_id
    ON expenses_db.income (apple_wallet_transaction_id) WHERE apple_wallet_transaction_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_income_user_apple_wallet_tx
    ON expenses_db.income (user_id, apple_wallet_transaction_id)
    WHERE apple_wallet_transaction_id IS NOT NULL;
