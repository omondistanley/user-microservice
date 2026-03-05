-- Income tracking + recurring expense templates.
-- Run: python run_migration.py migrations/005_income_and_recurring.sql

CREATE TABLE IF NOT EXISTS expenses_db.income (
    income_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    amount NUMERIC(19, 4) NOT NULL CHECK (amount >= 0),
    date DATE NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    income_type VARCHAR(32) NOT NULL DEFAULT 'other',
    source_label VARCHAR(255) NULL,
    description VARCHAR(2000) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_income_user_date
    ON expenses_db.income (user_id, date);
CREATE INDEX IF NOT EXISTS idx_income_user_type
    ON expenses_db.income (user_id, income_type);
CREATE INDEX IF NOT EXISTS idx_income_user_active
    ON expenses_db.income (user_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS expenses_db.recurring_expense (
    recurring_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    amount NUMERIC(19, 4) NOT NULL CHECK (amount >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    category_code SMALLINT NOT NULL,
    category_name VARCHAR(64) NOT NULL,
    description VARCHAR(2000) NULL,
    recurrence_rule VARCHAR(16) NOT NULL CHECK (recurrence_rule IN ('weekly', 'monthly', 'yearly')),
    next_due_date DATE NOT NULL,
    last_run_at TIMESTAMPTZ NULL,
    last_created_expense_id UUID NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recurring_user_active_due
    ON expenses_db.recurring_expense (user_id, is_active, next_due_date);
CREATE INDEX IF NOT EXISTS idx_recurring_user
    ON expenses_db.recurring_expense (user_id);
