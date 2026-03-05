-- Per-user settings (Phase 2 currency preference).
-- Run: python run_migration.py migrations/008_user_settings.sql

CREATE TABLE IF NOT EXISTS users_db.user_settings (
    user_id INTEGER PRIMARY KEY,
    default_currency CHAR(3) NOT NULL DEFAULT 'USD',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users_db.user_settings DROP CONSTRAINT IF EXISTS fk_user_settings_user;
ALTER TABLE users_db.user_settings ADD CONSTRAINT fk_user_settings_user
    FOREIGN KEY (user_id) REFERENCES users_db."user"(id) ON DELETE CASCADE;
