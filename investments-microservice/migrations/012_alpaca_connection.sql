-- Alpaca brokerage connections and source metadata for holdings
-- Run: python run_migration.py migrations/012_alpaca_connection.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS investments_db;

-- Per-user Alpaca connection (paper or live). Stores encrypted API credentials and metadata.
CREATE TABLE IF NOT EXISTS investments_db.alpaca_connection (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL UNIQUE,
    alpaca_account_id VARCHAR(64),
    api_key_encrypted TEXT,
    api_secret_encrypted TEXT,
    is_paper BOOLEAN NOT NULL DEFAULT TRUE,
    last_sync_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alpaca_connection_user
    ON investments_db.alpaca_connection (user_id);

-- Enrich holdings with source and external identifier so synced positions
-- (e.g. Alpaca) can be distinguished from manual entries and updated idempotently.
ALTER TABLE investments_db.holding
    ADD COLUMN IF NOT EXISTS source VARCHAR(32) NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS external_id VARCHAR(128);

CREATE INDEX IF NOT EXISTS idx_holding_user_source_external
    ON investments_db.holding (user_id, source, external_id);

