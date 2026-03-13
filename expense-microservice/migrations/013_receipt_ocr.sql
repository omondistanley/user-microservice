-- Receipt OCR: store raw text and extracted fields per receipt.
-- Run: python run_migration.py migrations/013_receipt_ocr.sql

CREATE TABLE IF NOT EXISTS expenses_db.receipt_ocr_result (
    receipt_id UUID PRIMARY KEY,
    raw_text TEXT NULL,
    extracted_json JSONB NULL DEFAULT '{}',
    ocr_run_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_receipt_ocr_receipt FOREIGN KEY (receipt_id) REFERENCES expenses_db.receipt(receipt_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_receipt_ocr_run_at ON expenses_db.receipt_ocr_result (ocr_run_at);
