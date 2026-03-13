-- Phase 5: Data retention policy config and purge targets.
-- Run: python run_migration.py migrations/014_retention_policy.sql

CREATE TABLE IF NOT EXISTS users_db.retention_policy (
    entity VARCHAR(64) PRIMARY KEY,
    retention_days INTEGER NOT NULL CHECK (retention_days >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Default policies (idempotent)
INSERT INTO users_db.retention_policy (entity, retention_days, is_active) VALUES
    ('audit_log', 365, true),
    ('password_reset_token', 7, true),
    ('user_notification', 90, true),
    ('refresh_token', 0, true)
ON CONFLICT (entity) DO NOTHING;
