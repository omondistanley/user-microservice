-- Round-up config and allow round_up source on goal contributions.
-- Run: python run_migration.py migrations/017_round_up_goal.sql

-- Allow 'round_up' as a contribution source (drop old check, add new)
ALTER TABLE expenses_db.goal_contribution DROP CONSTRAINT IF EXISTS goal_contribution_source_check;
ALTER TABLE expenses_db.goal_contribution
    ADD CONSTRAINT goal_contribution_source_check
    CHECK (source IN ('manual', 'auto_cashflow', 'round_up'));

-- Per-user, per-goal round-up configuration
CREATE TABLE IF NOT EXISTS expenses_db.round_up_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    goal_id UUID NOT NULL REFERENCES expenses_db.savings_goal(goal_id) ON DELETE CASCADE,
    round_to NUMERIC(19, 4) NOT NULL DEFAULT 1 CHECK (round_to > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, goal_id)
);

CREATE INDEX IF NOT EXISTS idx_round_up_config_user_active
    ON expenses_db.round_up_config (user_id, is_active);
