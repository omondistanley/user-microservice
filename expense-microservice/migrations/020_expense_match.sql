-- Link two expenses as the same transaction (e.g. bank import + manual entry).
-- In reports, exclude or collapse matched pairs (e.g. treat expense_id_b as duplicate).
-- Run: python run_migration.py migrations/020_expense_match.sql

CREATE TABLE IF NOT EXISTS expenses_db.expense_match (
    expense_id_a UUID NOT NULL,
    expense_id_b UUID NOT NULL,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (expense_id_a, expense_id_b),
    CONSTRAINT chk_expense_match_ordering CHECK (expense_id_a < expense_id_b),
    CONSTRAINT fk_expense_match_a FOREIGN KEY (expense_id_a) REFERENCES expenses_db.expense(expense_id) ON DELETE CASCADE,
    CONSTRAINT fk_expense_match_b FOREIGN KEY (expense_id_b) REFERENCES expenses_db.expense(expense_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_expense_match_reverse
    ON expenses_db.expense_match (expense_id_b, expense_id_a);
CREATE INDEX IF NOT EXISTS idx_expense_match_user ON expenses_db.expense_match (user_id);
