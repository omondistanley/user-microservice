-- Phase 3: Add optional household_id to budget.
-- Run: python run_migration.py migrations/003_household_scope.sql

ALTER TABLE budgets_db.budget ADD COLUMN IF NOT EXISTS household_id UUID NULL;
CREATE INDEX IF NOT EXISTS idx_budget_user_household_dates ON budgets_db.budget (user_id, household_id, start_date, end_date);
