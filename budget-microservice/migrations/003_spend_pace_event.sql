-- Spend-pace nudges: one per budget per period when spend is ahead of time.
-- Run: python run_migration.py migrations/003_spend_pace_event.sql

CREATE TABLE IF NOT EXISTS budgets_db.budget_spend_pace_event (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    budget_id UUID NOT NULL REFERENCES budgets_db.budget(budget_id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    spent_amount NUMERIC(19, 4) NOT NULL,
    budget_amount NUMERIC(19, 4) NOT NULL,
    spent_ratio NUMERIC(9, 4) NOT NULL,
    time_ratio NUMERIC(9, 4) NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_budget_spend_pace_event_dedupe
    ON budgets_db.budget_spend_pace_event (user_id, budget_id, period_start, period_end);
