-- Phase 7: Provider field for bank connector abstraction.
ALTER TABLE expenses_db.plaid_item ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL DEFAULT 'plaid';
