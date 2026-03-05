-- Tags support for expenses.
-- Run: python run_migration.py migrations/006_tags.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS expenses_db.tag (
    tag_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    name VARCHAR(64) NOT NULL,
    slug VARCHAR(80) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tag_user_lower_name
    ON expenses_db.tag (user_id, lower(name));
CREATE UNIQUE INDEX IF NOT EXISTS idx_tag_user_slug
    ON expenses_db.tag (user_id, slug);
CREATE INDEX IF NOT EXISTS idx_tag_user_created
    ON expenses_db.tag (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS expenses_db.expense_tag (
    expense_id UUID NOT NULL,
    tag_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (expense_id, tag_id)
);

ALTER TABLE expenses_db.expense_tag DROP CONSTRAINT IF EXISTS fk_expense_tag_expense;
ALTER TABLE expenses_db.expense_tag ADD CONSTRAINT fk_expense_tag_expense
    FOREIGN KEY (expense_id) REFERENCES expenses_db.expense(expense_id) ON DELETE CASCADE;

ALTER TABLE expenses_db.expense_tag DROP CONSTRAINT IF EXISTS fk_expense_tag_tag;
ALTER TABLE expenses_db.expense_tag ADD CONSTRAINT fk_expense_tag_tag
    FOREIGN KEY (tag_id) REFERENCES expenses_db.tag(tag_id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_expense_tag_expense
    ON expenses_db.expense_tag (expense_id);
CREATE INDEX IF NOT EXISTS idx_expense_tag_tag
    ON expenses_db.expense_tag (tag_id);
