-- Exchange rates for currency conversion (daily snapshots).
-- Run: python run_migration.py migrations/007_exchange_rate.sql

CREATE TABLE IF NOT EXISTS expenses_db.exchange_rate (
    base_currency CHAR(3) NOT NULL,
    quote_currency CHAR(3) NOT NULL,
    rate NUMERIC(19, 10) NOT NULL CHECK (rate > 0),
    rate_date DATE NOT NULL,
    source VARCHAR(32) NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (base_currency, quote_currency, rate_date, source)
);

CREATE INDEX IF NOT EXISTS idx_exchange_rate_pair_date
    ON expenses_db.exchange_rate (base_currency, quote_currency, rate_date DESC);
CREATE INDEX IF NOT EXISTS idx_exchange_rate_date
    ON expenses_db.exchange_rate (rate_date DESC);
