-- Household table for Phase 3 (shared scope).
-- Run: python run_migration.py migrations/009_household.sql

CREATE TABLE IF NOT EXISTS users_db.household (
    household_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users_db.household DROP CONSTRAINT IF EXISTS fk_household_owner;
ALTER TABLE users_db.household ADD CONSTRAINT fk_household_owner
    FOREIGN KEY (owner_user_id) REFERENCES users_db."user"(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_household_owner ON users_db.household (owner_user_id);
