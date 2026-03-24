-- Migration 026: Gmail OAuth token storage + Pub/Sub watch metadata
-- Stores encrypted OAuth2 tokens for Gmail receipt ingestion.
-- Token data is encrypted at the application layer (Fernet) before insertion.

BEGIN;

CREATE TABLE IF NOT EXISTS expenses_db.gmail_oauth_token (
    token_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         INTEGER     NOT NULL,
    -- Fernet-encrypted JSON blob: {access_token, refresh_token, token_uri, client_id, client_secret, scopes}
    encrypted_token TEXT        NOT NULL,
    -- Gmail watch subscription metadata
    history_id      BIGINT,                          -- last processed historyId
    watch_expiry    TIMESTAMPTZ,                     -- Pub/Sub watch expires at this time
    watch_resource  TEXT,                            -- Pub/Sub resource name from watch() response
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_gmail_oauth_token_user UNIQUE (user_id)
);

CREATE INDEX IF NOT EXISTS idx_gmail_oauth_token_user
    ON expenses_db.gmail_oauth_token (user_id);

-- Tracks individual receipt emails processed to prevent double-counting
CREATE TABLE IF NOT EXISTS expenses_db.gmail_receipt_processed (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         INTEGER     NOT NULL,
    message_id      TEXT        NOT NULL,    -- Gmail message ID
    thread_id       TEXT,
    subject         TEXT,
    from_address    TEXT,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expense_id      UUID,                   -- linked expense if one was created
    CONSTRAINT uq_gmail_receipt_user_message UNIQUE (user_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_gmail_receipt_processed_user
    ON expenses_db.gmail_receipt_processed (user_id, processed_at DESC);

COMMIT;
