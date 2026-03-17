-- Security universe: cache for API-sourced symbol metadata (Option B + C).
-- Populated by bootstrap job (Finnhub/Alpha Vantage) and on-demand resolver.
-- Run: python run_migration.py migrations/004_security_universe.sql

CREATE TABLE IF NOT EXISTS investments_db.security_universe (
    symbol VARCHAR(32) PRIMARY KEY,
    full_name VARCHAR(512) NULL,
    sector VARCHAR(64) NULL,
    risk_band VARCHAR(32) NULL,
    description TEXT NULL,
    asset_type VARCHAR(32) NULL,
    source_provider VARCHAR(32) NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE investments_db.security_universe IS 'Cached security metadata from Finnhub/Alpha Vantage, used by get_analyst_universe and get_security_info';
COMMENT ON COLUMN investments_db.security_universe.sector IS 'Normalized sector: technology, healthcare, financials, etc.';
COMMENT ON COLUMN investments_db.security_universe.risk_band IS 'conservative | balanced | aggressive';
COMMENT ON COLUMN investments_db.security_universe.source_provider IS 'finnhub | alphavantage | bootstrap | on_demand';

CREATE INDEX IF NOT EXISTS idx_security_universe_sector
    ON investments_db.security_universe (sector);
CREATE INDEX IF NOT EXISTS idx_security_universe_updated_at
    ON investments_db.security_universe (updated_at);
