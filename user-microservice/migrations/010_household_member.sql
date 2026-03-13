-- Household membership for Phase 3.
-- Run: python run_migration.py migrations/010_household_member.sql

CREATE TABLE IF NOT EXISTS users_db.household_member (
    household_id UUID NOT NULL,
    user_id INTEGER NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'member',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    invited_by_user_id INTEGER NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, user_id)
);

ALTER TABLE users_db.household_member DROP CONSTRAINT IF EXISTS fk_household_member_household;
ALTER TABLE users_db.household_member ADD CONSTRAINT fk_household_member_household
    FOREIGN KEY (household_id) REFERENCES users_db.household(household_id) ON DELETE CASCADE;
ALTER TABLE users_db.household_member DROP CONSTRAINT IF EXISTS fk_household_member_user;
ALTER TABLE users_db.household_member ADD CONSTRAINT fk_household_member_user
    FOREIGN KEY (user_id) REFERENCES users_db."user"(id) ON DELETE CASCADE;
ALTER TABLE users_db.household_member DROP CONSTRAINT IF EXISTS fk_household_member_invited_by;
ALTER TABLE users_db.household_member ADD CONSTRAINT fk_household_member_invited_by
    FOREIGN KEY (invited_by_user_id) REFERENCES users_db."user"(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_household_member_user ON users_db.household_member (user_id);
CREATE INDEX IF NOT EXISTS idx_household_member_status ON users_db.household_member (status);
