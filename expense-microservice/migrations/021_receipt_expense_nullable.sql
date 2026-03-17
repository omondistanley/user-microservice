-- Allow receipts without an expense (upload first, link later).
-- Run: python run_migration.py migrations/021_receipt_expense_nullable.sql

ALTER TABLE expenses_db.receipt
    ALTER COLUMN expense_id DROP NOT NULL;

-- Drop FK so we can have NULL expense_id; re-add to keep referential integrity when set
ALTER TABLE expenses_db.receipt DROP CONSTRAINT IF EXISTS fk_receipt_expense;
ALTER TABLE expenses_db.receipt
    ADD CONSTRAINT fk_receipt_expense
    FOREIGN KEY (expense_id) REFERENCES expenses_db.expense(expense_id) ON DELETE SET NULL;

-- ON DELETE SET NULL requires expense_id to be nullable; FK allows NULL
CREATE INDEX IF NOT EXISTS idx_receipt_expense_id ON expenses_db.receipt (expense_id) WHERE expense_id IS NOT NULL;
