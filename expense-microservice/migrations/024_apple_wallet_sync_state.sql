-- Apple Wallet per-user sync state tracking.
-- Stores the last time the /since-last-sync endpoint was called for a given user,
-- so iOS Shortcuts can always fetch only new transactions since the previous tap.
-- Run: python run_migration.py migrations/024_apple_wallet_sync_state.sql

CREATE TABLE IF NOT EXISTS expenses_db.apple_wallet_sync_state (
    user_id          INTEGER PRIMARY KEY,
    last_sync_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Allow upsert from the service
CREATE INDEX IF NOT EXISTS idx_aws_user_id ON expenses_db.apple_wallet_sync_state (user_id);
