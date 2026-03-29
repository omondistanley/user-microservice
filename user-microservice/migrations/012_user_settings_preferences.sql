-- Add theme and notification preference fields to user settings.
-- Run: python run_migration.py migrations/012_user_settings_preferences.sql

ALTER TABLE users_db.user_settings
    ADD COLUMN IF NOT EXISTS theme_preference VARCHAR(10) NOT NULL DEFAULT 'system';

ALTER TABLE users_db.user_settings
    ADD COLUMN IF NOT EXISTS push_notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE users_db.user_settings
    ADD COLUMN IF NOT EXISTS email_notifications_enabled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE users_db.user_settings DROP CONSTRAINT IF EXISTS chk_user_settings_theme_preference;
ALTER TABLE users_db.user_settings
    ADD CONSTRAINT chk_user_settings_theme_preference
    CHECK (theme_preference IN ('light', 'dark', 'system'));
