-- Phase 7: Webhook event idempotency (dedupe by provider + event_id).
CREATE TABLE IF NOT EXISTS users_db.webhook_event (
    id BIGSERIAL PRIMARY KEY,
    provider VARCHAR(64) NOT NULL,
    event_id VARCHAR(255) NOT NULL,
    payload_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(provider, event_id)
);

CREATE INDEX IF NOT EXISTS idx_webhook_event_provider_created ON users_db.webhook_event (provider, created_at DESC);
