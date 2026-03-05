-- Refresh tokens for token rotation (POST /token/refresh).
-- Run: python run_migration.py migrations/002_refresh_token.sql
CREATE TABLE IF NOT EXISTS users_db.refresh_token (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users_db.refresh_token DROP CONSTRAINT IF EXISTS fk_refresh_token_user;
ALTER TABLE users_db.refresh_token ADD CONSTRAINT fk_refresh_token_user
    FOREIGN KEY (user_id) REFERENCES users_db."user"(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_refresh_token_hash ON users_db.refresh_token (token_hash);
CREATE INDEX IF NOT EXISTS idx_refresh_token_expires ON users_db.refresh_token (expires_at);
