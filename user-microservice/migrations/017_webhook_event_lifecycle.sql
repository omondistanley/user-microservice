-- Phase 8: Webhook event lifecycle fields for async processing/retry.
ALTER TABLE users_db.webhook_event
    ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'processed', 'failed')),
    ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS last_error TEXT NULL,
    ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS headers_json JSONB NULL;

CREATE INDEX IF NOT EXISTS idx_webhook_event_status_retry
    ON users_db.webhook_event (status, next_retry_at, created_at);
