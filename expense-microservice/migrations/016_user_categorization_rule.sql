-- User-defined categorization rules: apply category and/or tags when conditions match.
-- Run: python run_migration.py migrations/016_user_categorization_rule.sql

CREATE SCHEMA IF NOT EXISTS expenses_db;

CREATE TABLE IF NOT EXISTS expenses_db.user_categorization_rule (
    rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    condition_type VARCHAR(64) NOT NULL,
    condition_value JSONB NOT NULL DEFAULT '{}',
    set_category_code SMALLINT NULL,
    set_tag_names TEXT[] NULL,
    notify_on_match BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_categorization_rule_user_active
    ON expenses_db.user_categorization_rule (user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_user_categorization_rule_priority
    ON expenses_db.user_categorization_rule (user_id, priority);
