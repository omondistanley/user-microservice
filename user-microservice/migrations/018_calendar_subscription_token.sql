-- Phase 8: Revocable calendar subscription token for ICS feeds.
CREATE TABLE IF NOT EXISTS users_db.calendar_subscription_token (
    token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ NULL,
    CONSTRAINT fk_calendar_token_user
        FOREIGN KEY (user_id) REFERENCES users_db."user"(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_subscription_active_user
    ON users_db.calendar_subscription_token (user_id)
    WHERE is_active = TRUE;
