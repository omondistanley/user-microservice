-- Migration 016: Add account_type and role_label columns to holding table
-- account_type: tracks whether holding is in taxable, IRA, Roth IRA, 401k etc.
-- role_label: Core / Growth / Income / Hedge / Speculative classification

ALTER TABLE investments_db.holding
  ADD COLUMN IF NOT EXISTS account_type VARCHAR(32) DEFAULT 'taxable',
  ADD COLUMN IF NOT EXISTS role_label   VARCHAR(32) DEFAULT NULL;

COMMENT ON COLUMN investments_db.holding.account_type IS 'taxable | traditional_ira | roth_ira | 401k | hsa | other';
COMMENT ON COLUMN investments_db.holding.role_label   IS 'core | growth | income | hedge | speculative | null (unclassified)';
