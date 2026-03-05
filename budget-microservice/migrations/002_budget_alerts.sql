-- Budget alert configuration and event history.
-- Run: python run_migration.py migrations/002_budget_alerts.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS budgets_db.budget_alert_config (
    config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    budget_id UUID NOT NULL,
    threshold_percent NUMERIC(5, 2) NOT NULL CHECK (threshold_percent > 0 AND threshold_percent <= 1000),
    channel VARCHAR(16) NOT NULL CHECK (channel IN ('in_app', 'email')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE budgets_db.budget_alert_config DROP CONSTRAINT IF EXISTS fk_budget_alert_config_budget;
ALTER TABLE budgets_db.budget_alert_config ADD CONSTRAINT fk_budget_alert_config_budget
    FOREIGN KEY (budget_id) REFERENCES budgets_db.budget(budget_id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_budget_alert_config_user_budget
    ON budgets_db.budget_alert_config (user_id, budget_id);
CREATE INDEX IF NOT EXISTS idx_budget_alert_config_budget_active
    ON budgets_db.budget_alert_config (budget_id, is_active);

CREATE TABLE IF NOT EXISTS budgets_db.budget_alert_event (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    budget_id UUID NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    threshold_percent NUMERIC(5, 2) NOT NULL,
    spent_amount NUMERIC(19, 4) NOT NULL,
    budget_amount NUMERIC(19, 4) NOT NULL,
    channel VARCHAR(16) NOT NULL CHECK (channel IN ('in_app', 'email')),
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE budgets_db.budget_alert_event DROP CONSTRAINT IF EXISTS fk_budget_alert_event_budget;
ALTER TABLE budgets_db.budget_alert_event ADD CONSTRAINT fk_budget_alert_event_budget
    FOREIGN KEY (budget_id) REFERENCES budgets_db.budget(budget_id) ON DELETE CASCADE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_budget_alert_event_dedupe
    ON budgets_db.budget_alert_event (user_id, budget_id, period_start, period_end, threshold_percent, channel);
CREATE INDEX IF NOT EXISTS idx_budget_alert_event_user_sent
    ON budgets_db.budget_alert_event (user_id, sent_at DESC);
