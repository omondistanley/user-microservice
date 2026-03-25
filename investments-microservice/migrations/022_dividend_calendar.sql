CREATE TABLE IF NOT EXISTS dividend_calendar (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    symbol VARCHAR(16) NOT NULL,
    ex_date DATE NOT NULL,
    pay_date DATE,
    amount_per_share NUMERIC(12,4),
    frequency VARCHAR(16),  -- 'quarterly', 'monthly', 'annual', 'semi-annual'
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, symbol, ex_date)
);
CREATE INDEX IF NOT EXISTS idx_dividend_calendar_user_date ON dividend_calendar(user_id, ex_date);
