-- Add active_household_id to user_settings for Phase 3 scope.
-- Run: python run_migration.py migrations/011_active_household.sql

ALTER TABLE users_db.user_settings ADD COLUMN IF NOT EXISTS active_household_id UUID NULL;

ALTER TABLE users_db.user_settings DROP CONSTRAINT IF EXISTS fk_user_settings_active_household;
ALTER TABLE users_db.user_settings ADD CONSTRAINT fk_user_settings_active_household
    FOREIGN KEY (active_household_id) REFERENCES users_db.household(household_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_user_settings_active_household ON users_db.user_settings (active_household_id);
