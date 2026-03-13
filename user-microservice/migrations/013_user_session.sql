-- Phase 5: Session tracking tied to refresh tokens (no 2FA).
-- Run: python run_migration.py migrations/013_user_session.sql

CREATE TABLE IF NOT EXISTS users_db.user_session (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    device_meta VARCHAR(512) NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ NULL,
    CONSTRAINT fk_user_session_user FOREIGN KEY (user_id) REFERENCES users_db."user"(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_session_user ON users_db.user_session (user_id);
CREATE INDEX IF NOT EXISTS idx_user_session_revoked ON users_db.user_session (user_id, revoked_at);

ALTER TABLE users_db.refresh_token ADD COLUMN IF NOT EXISTS session_id UUID NULL;
ALTER TABLE users_db.refresh_token DROP CONSTRAINT IF EXISTS fk_refresh_token_session;
ALTER TABLE users_db.refresh_token ADD CONSTRAINT fk_refresh_token_session
    FOREIGN KEY (session_id) REFERENCES users_db.user_session(session_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_refresh_token_session ON users_db.refresh_token (session_id);
