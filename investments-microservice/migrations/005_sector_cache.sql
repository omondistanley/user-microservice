-- Sector cache: symbol -> sector with TTL (updated_at). Used for sector exposure breakdown.
-- Run: python run_migration.py migrations/005_sector_cache.sql

CREATE TABLE IF NOT EXISTS investments_db.sector_cache (
    symbol VARCHAR(32) PRIMARY KEY,
    sector VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sector_cache_updated_at
    ON investments_db.sector_cache (updated_at);

COMMENT ON TABLE investments_db.sector_cache IS 'Cached sector per symbol (e.g. from yfinance), TTL enforced in app (e.g. 24h)';
