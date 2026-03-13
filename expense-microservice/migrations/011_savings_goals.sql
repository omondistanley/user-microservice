-- Phase 4: Savings goals and contributions.
-- Run: python run_migration.py migrations/011_savings_goals.sql

CREATE TABLE IF NOT EXISTS expenses_db.savings_goal (
    goal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    household_id UUID NULL,
    name VARCHAR(255) NOT NULL,
    target_amount NUMERIC(19, 4) NOT NULL CHECK (target_amount >= 0),
    target_currency CHAR(3) NOT NULL DEFAULT 'USD',
    target_date DATE NULL,
    start_amount NUMERIC(19, 4) NOT NULL DEFAULT 0 CHECK (start_amount >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_savings_goal_user ON expenses_db.savings_goal (user_id);
CREATE INDEX IF NOT EXISTS idx_savings_goal_household_active ON expenses_db.savings_goal (household_id, is_active);
CREATE INDEX IF NOT EXISTS idx_savings_goal_user_active ON expenses_db.savings_goal (user_id, is_active);

CREATE TABLE IF NOT EXISTS expenses_db.goal_contribution (
    contribution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL,
    user_id INTEGER NOT NULL,
    amount NUMERIC(19, 4) NOT NULL CHECK (amount >= 0),
    contribution_date DATE NOT NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'auto_cashflow')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_goal_contribution_goal FOREIGN KEY (goal_id) REFERENCES expenses_db.savings_goal(goal_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_goal_contribution_goal_date ON expenses_db.goal_contribution (goal_id, contribution_date);
CREATE INDEX IF NOT EXISTS idx_goal_contribution_user ON expenses_db.goal_contribution (user_id);
