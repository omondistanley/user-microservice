-- Fundamental metrics cache for quality scoring (P/E, ROE, margins, etc.).
-- Run: python run_migration.py migrations/010_fundamental_snapshot.sql

CREATE TABLE IF NOT EXISTS investments_db.fundamental_snapshot (
    symbol VARCHAR(32) NOT NULL,
    period_end DATE NOT NULL,
    metrics_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, period_end)
);

CREATE INDEX IF NOT EXISTS idx_fundamental_snapshot_symbol ON investments_db.fundamental_snapshot (symbol);
CREATE INDEX IF NOT EXISTS idx_fundamental_snapshot_updated ON investments_db.fundamental_snapshot (updated_at);

COMMENT ON TABLE investments_db.fundamental_snapshot IS 'Cached fundamental metrics (yfinance/Finnhub) for quality scoring';
