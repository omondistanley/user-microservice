-- Recurring budget templates (user-defined cadence; separate from period budget rows).
CREATE TABLE IF NOT EXISTS budgets_db.recurring_budget (
    recurring_budget_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    name VARCHAR(255) NULL,
    category_code SMALLINT NOT NULL CHECK (category_code >= 1 AND category_code <= 8),
    amount NUMERIC(19, 4) NOT NULL CHECK (amount >= 0),
    cadence VARCHAR(16) NOT NULL CHECK (cadence IN ('weekly', 'monthly', 'yearly')),
    start_date DATE NOT NULL,
    next_period_start DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    household_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recurring_budget_user
    ON budgets_db.recurring_budget (user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_recurring_budget_user_category
    ON budgets_db.recurring_budget (user_id, category_code);
