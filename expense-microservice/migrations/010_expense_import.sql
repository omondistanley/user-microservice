-- Phase 3: CSV import job and rows for dry-run and commit.
-- Run: python run_migration.py migrations/010_expense_import.sql

CREATE TABLE IF NOT EXISTS expenses_db.expense_import_job (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    household_id UUID NULL,
    filename VARCHAR(512) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'validated', 'committed', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_expense_import_job_user_status ON expenses_db.expense_import_job (user_id, status);

CREATE TABLE IF NOT EXISTS expenses_db.expense_import_row (
    job_id UUID NOT NULL,
    row_number INTEGER NOT NULL,
    raw_payload JSONB NULL,
    normalized_payload JSONB NULL,
    validation_error TEXT NULL,
    is_duplicate BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, row_number)
);

ALTER TABLE expenses_db.expense_import_row DROP CONSTRAINT IF EXISTS fk_expense_import_row_job;
ALTER TABLE expenses_db.expense_import_row ADD CONSTRAINT fk_expense_import_row_job
    FOREIGN KEY (job_id) REFERENCES expenses_db.expense_import_job(job_id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_expense_import_row_job ON expenses_db.expense_import_row (job_id);
