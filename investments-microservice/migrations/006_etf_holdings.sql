-- ETF composition: underlying constituents with weights for look-through exposure.
-- Run: python run_migration.py migrations/006_etf_holdings.sql

CREATE TABLE IF NOT EXISTS investments_db.etf_holding (
    etf_symbol VARCHAR(32) NOT NULL,
    constituent_symbol VARCHAR(32) NOT NULL,
    weight_pct NUMERIC(8, 4) NOT NULL,
    as_of_date DATE NOT NULL,
    source VARCHAR(64) NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (etf_symbol, constituent_symbol)
);

CREATE INDEX IF NOT EXISTS idx_etf_holding_etf ON investments_db.etf_holding (etf_symbol);
CREATE INDEX IF NOT EXISTS idx_etf_holding_constituent ON investments_db.etf_holding (constituent_symbol);
CREATE INDEX IF NOT EXISTS idx_etf_holding_as_of ON investments_db.etf_holding (as_of_date);

COMMENT ON TABLE investments_db.etf_holding IS 'ETF constituent weights for look-through exposure (iShares/Vanguard/SSGA)';
