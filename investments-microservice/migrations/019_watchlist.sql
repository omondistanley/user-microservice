-- Migration 019: Watchlist table for price alerts
CREATE TABLE IF NOT EXISTS watchlist (
    watchlist_id  SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    symbol        VARCHAR(20) NOT NULL,
    target_price  NUMERIC(18,4),
    direction     VARCHAR(10) NOT NULL DEFAULT 'below',  -- above | below
    notes         TEXT,
    alerted_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_watchlist_user_symbol ON watchlist(user_id, symbol);
