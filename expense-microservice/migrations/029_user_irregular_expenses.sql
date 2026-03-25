-- Migration 029: User irregular expenses table
-- Stores user-confirmed or auto-detected irregular annual/quarterly expenses
-- Used to compute the irregular expense reserve in the surplus waterfall

CREATE TABLE IF NOT EXISTS user_irregular_expense (
    irregular_id     SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL,
    household_id     UUID DEFAULT NULL,
    label            VARCHAR(128) NOT NULL,
    estimated_amount NUMERIC(19,4) NOT NULL CHECK (estimated_amount > 0),
    frequency        VARCHAR(32) NOT NULL DEFAULT 'annual',  -- annual | quarterly | one_off
    next_due_date    DATE DEFAULT NULL,
    is_manual        BOOLEAN NOT NULL DEFAULT FALSE,
    confidence       VARCHAR(10) NOT NULL DEFAULT 'low',  -- high | low
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_irregular_expense_user
    ON user_irregular_expense (user_id);

CREATE INDEX IF NOT EXISTS idx_irregular_expense_household
    ON user_irregular_expense (household_id) WHERE household_id IS NOT NULL;
