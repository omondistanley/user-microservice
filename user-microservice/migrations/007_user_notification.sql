-- In-app notifications for authenticated users.
-- Run: python run_migration.py migrations/007_user_notification.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users_db.user_notification (
    notification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    type VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT false,
    payload_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at TIMESTAMPTZ NULL
);

ALTER TABLE users_db.user_notification DROP CONSTRAINT IF EXISTS fk_user_notification_user;
ALTER TABLE users_db.user_notification ADD CONSTRAINT fk_user_notification_user
    FOREIGN KEY (user_id) REFERENCES users_db."user"(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_user_notification_user_created
    ON users_db.user_notification (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_notification_user_unread
    ON users_db.user_notification (user_id, is_read, created_at DESC);
