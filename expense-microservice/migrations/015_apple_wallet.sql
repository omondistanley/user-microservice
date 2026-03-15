-- Apple Wallet (Shortcuts) webhook: expense source tracking and dedup.
-- Run: python run_migration.py migrations/015_apple_wallet.sql

ALTER TABLE expenses_db.expense
    ADD COLUMN IF NOT EXISTS apple_wallet_transaction_id VARCHAR(64) NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_expense_apple_wallet_transaction_id
    ON expenses_db.expense (apple_wallet_transaction_id) WHERE apple_wallet_transaction_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_expense_user_apple_wallet_tx ON expenses_db.expense (user_id, apple_wallet_transaction_id)
    WHERE apple_wallet_transaction_id IS NOT NULL;
