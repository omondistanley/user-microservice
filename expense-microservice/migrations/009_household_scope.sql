-- Phase 3: Add optional household_id to expense, income, recurring_expense.
-- Run: python run_migration.py migrations/009_household_scope.sql

ALTER TABLE expenses_db.expense ADD COLUMN IF NOT EXISTS household_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_expense_user_household_date ON expenses_db.expense (user_id, household_id, date) WHERE deleted_at IS NULL;

ALTER TABLE expenses_db.income ADD COLUMN IF NOT EXISTS household_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_income_user_household_date ON expenses_db.income (user_id, household_id, date) WHERE deleted_at IS NULL;

ALTER TABLE expenses_db.recurring_expense ADD COLUMN IF NOT EXISTS household_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_recurring_user_household ON expenses_db.recurring_expense (user_id, household_id);
