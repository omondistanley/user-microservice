-- Migration 021: ETF constituents table for overlap detection
-- Richer than etf_holding: tracks fetch date for staleness checks
CREATE TABLE IF NOT EXISTS etf_constituent (
    constituent_id SERIAL PRIMARY KEY,
    etf_symbol     VARCHAR(20) NOT NULL,
    holding_symbol VARCHAR(20) NOT NULL,
    weight_pct     NUMERIC(8,4) NOT NULL DEFAULT 0,
    fetched_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_etf_constituent_etf_holding
    ON etf_constituent(etf_symbol, holding_symbol, fetched_date);
CREATE INDEX IF NOT EXISTS idx_etf_constituent_etf ON etf_constituent(etf_symbol);
