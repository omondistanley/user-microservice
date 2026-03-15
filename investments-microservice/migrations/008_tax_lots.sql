-- Tax lots and transaction log for cost basis and wash-sale (tax-loss harvesting).
-- Run: python run_migration.py migrations/008_tax_lots.sql

CREATE TABLE IF NOT EXISTS investments_db.tax_lot (
    lot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    holding_id UUID NOT NULL,
    quantity NUMERIC(19, 6) NOT NULL CHECK (quantity > 0),
    cost_per_share NUMERIC(19, 4) NOT NULL CHECK (cost_per_share >= 0),
    purchase_date DATE NOT NULL,
    source VARCHAR(64) NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_tax_lot_holding FOREIGN KEY (holding_id) REFERENCES investments_db.holding(holding_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tax_lot_holding ON investments_db.tax_lot (holding_id);
CREATE INDEX IF NOT EXISTS idx_tax_lot_purchase_date ON investments_db.tax_lot (purchase_date);

CREATE TABLE IF NOT EXISTS investments_db.transaction (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    type VARCHAR(8) NOT NULL CHECK (type IN ('buy', 'sell')),
    quantity NUMERIC(19, 6) NOT NULL CHECK (quantity > 0),
    transaction_date DATE NOT NULL,
    lot_id_ref UUID NULL REFERENCES investments_db.tax_lot(lot_id) ON DELETE SET NULL,
    notes VARCHAR(512) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_transaction_user_symbol ON investments_db.transaction (user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_transaction_date ON investments_db.transaction (user_id, symbol, transaction_date);

COMMENT ON TABLE investments_db.tax_lot IS 'Cost basis lots per holding for tax-loss harvesting';
COMMENT ON TABLE investments_db.transaction IS 'Buy/sell log for wash-sale lookback';
