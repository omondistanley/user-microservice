-- Phase 9: OAuth-backed calendar connections (Google first, provider-extensible).
CREATE TABLE IF NOT EXISTS users_db.calendar_oauth_connection (
    connection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    provider VARCHAR(32) NOT NULL,
    provider_account_email VARCHAR(320),
    provider_calendar_id VARCHAR(255),
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_expires_at TIMESTAMPTZ,
    scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_calendar_oauth_user
        FOREIGN KEY (user_id) REFERENCES users_db."user"(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_oauth_user_provider
    ON users_db.calendar_oauth_connection (user_id, provider);

CREATE INDEX IF NOT EXISTS idx_calendar_oauth_active_user
    ON users_db.calendar_oauth_connection (user_id)
    WHERE is_active = TRUE;
