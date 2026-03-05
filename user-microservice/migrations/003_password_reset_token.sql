-- Password reset tokens for forgot-password flow (short-lived, e.g. 1 hour).
-- Run: python run_migration.py migrations/003_password_reset_token.sql
CREATE TABLE IF NOT EXISTS users_db.password_reset_token (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users_db.password_reset_token DROP CONSTRAINT IF EXISTS fk_password_reset_token_user;
ALTER TABLE users_db.password_reset_token ADD CONSTRAINT fk_password_reset_token_user
    FOREIGN KEY (user_id) REFERENCES users_db."user"(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_password_reset_token_hash ON users_db.password_reset_token (token_hash);
CREATE INDEX IF NOT EXISTS idx_password_reset_token_expires ON users_db.password_reset_token (expires_at);
