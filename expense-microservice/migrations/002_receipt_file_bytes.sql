-- Add BLOB column for receipt file storage (db backend).
-- Run: python run_migration.py migrations/002_receipt_file_bytes.sql

ALTER TABLE expenses_db.receipt ADD COLUMN IF NOT EXISTS file_bytes BYTEA NULL;
