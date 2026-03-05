-- Idempotency keys for POST /api/v1/expenses (optional Idempotency-Key header).
-- Run: python run_migration.py migrations/003_idempotency.sql

CREATE TABLE IF NOT EXISTS expenses_db.idempotency (
    user_id INTEGER NOT NULL,
    idempotency_key VARCHAR(255) NOT NULL,
    expense_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_idempotency_created ON expenses_db.idempotency (created_at);
