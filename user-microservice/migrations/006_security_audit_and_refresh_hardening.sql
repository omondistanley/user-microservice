-- Security hardening for refresh tokens + audit trail.
-- Run: python run_migration.py migrations/006_security_audit_and_refresh_hardening.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE users_db.refresh_token
    ADD COLUMN IF NOT EXISTS family_id UUID,
    ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ NULL;

UPDATE users_db.refresh_token
SET family_id = gen_random_uuid()
WHERE family_id IS NULL;

ALTER TABLE users_db.refresh_token
    ALTER COLUMN family_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_refresh_token_user_id
    ON users_db.refresh_token (user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_token_user_family
    ON users_db.refresh_token (user_id, family_id);
CREATE INDEX IF NOT EXISTS idx_refresh_token_user_revoked
    ON users_db.refresh_token (user_id, revoked_at);

CREATE TABLE IF NOT EXISTS users_db.audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NULL,
    action VARCHAR(64) NOT NULL,
    ip_address INET NULL,
    request_id VARCHAR(64) NULL,
    details JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_user_created_at
    ON users_db.audit_log (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action_created_at
    ON users_db.audit_log (action, created_at DESC);
