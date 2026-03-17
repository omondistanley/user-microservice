-- Sentiment snapshots per symbol/day (FinBERT on news), for 7d rolling average and alerts.
-- Run: python run_migration.py migrations/011_sentiment_snapshot.sql

CREATE TABLE IF NOT EXISTS investments_db.sentiment_snapshot (
    symbol VARCHAR(32) NOT NULL,
    snapshot_date DATE NOT NULL,
    score NUMERIC(5, 4) NOT NULL,
    article_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_sentiment_snapshot_symbol ON investments_db.sentiment_snapshot (symbol);
CREATE INDEX IF NOT EXISTS idx_sentiment_snapshot_date ON investments_db.sentiment_snapshot (snapshot_date);

COMMENT ON TABLE investments_db.sentiment_snapshot IS 'Daily sentiment score from FinBERT on news, score in [-1, 1]';
