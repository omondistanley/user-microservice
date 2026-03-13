-- Phase 7: Digest config (email/Slack, frequency, scope).
CREATE TABLE IF NOT EXISTS users_db.digest_config (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    frequency VARCHAR(16) NOT NULL DEFAULT 'weekly' CHECK (frequency IN ('weekly', 'monthly')),
    channel VARCHAR(16) NOT NULL DEFAULT 'email' CHECK (channel IN ('email', 'slack_webhook')),
    channel_target VARCHAR(512) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_sent_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_digest_config_user FOREIGN KEY (user_id) REFERENCES users_db."user"(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_digest_config_user_channel ON users_db.digest_config (user_id, channel);
CREATE INDEX IF NOT EXISTS idx_digest_config_active ON users_db.digest_config (is_active, frequency);
