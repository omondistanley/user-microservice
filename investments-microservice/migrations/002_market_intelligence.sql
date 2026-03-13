-- Phase 2+: market data, analytics snapshots, risk profiles, recommendations.

CREATE TABLE IF NOT EXISTS investments_db.market_quote (
    symbol VARCHAR(32) NOT NULL,
    provider VARCHAR(32) NOT NULL,
    quote_currency CHAR(3) NOT NULL DEFAULT 'USD',
    price NUMERIC(19, 6) NOT NULL CHECK (price >= 0),
    as_of TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    stale_seconds INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, provider, as_of)
);
CREATE INDEX IF NOT EXISTS idx_market_quote_symbol_latest
    ON investments_db.market_quote (symbol, as_of DESC);

CREATE TABLE IF NOT EXISTS investments_db.price_bar (
    symbol VARCHAR(32) NOT NULL,
    provider VARCHAR(32) NOT NULL,
    bar_interval VARCHAR(16) NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    open NUMERIC(19, 6) NOT NULL,
    high NUMERIC(19, 6) NOT NULL,
    low NUMERIC(19, 6) NOT NULL,
    close NUMERIC(19, 6) NOT NULL,
    volume NUMERIC(24, 2) NULL,
    quote_currency CHAR(3) NOT NULL DEFAULT 'USD',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, provider, bar_interval, ts)
);
CREATE INDEX IF NOT EXISTS idx_price_bar_symbol_interval_ts
    ON investments_db.price_bar (symbol, bar_interval, ts DESC);

CREATE TABLE IF NOT EXISTS investments_db.portfolio_snapshot (
    snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,
    total_market_value NUMERIC(19, 4) NOT NULL DEFAULT 0,
    total_cost_basis NUMERIC(19, 4) NOT NULL DEFAULT 0,
    unrealized_pnl NUMERIC(19, 4) NOT NULL DEFAULT 0,
    daily_return NUMERIC(19, 8) NULL,
    rolling_volatility NUMERIC(19, 8) NULL,
    sharpe_ratio NUMERIC(19, 8) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshot_user_date
    ON investments_db.portfolio_snapshot (user_id, snapshot_date DESC);

CREATE TABLE IF NOT EXISTS investments_db.risk_profile (
    user_id INTEGER PRIMARY KEY,
    risk_tolerance VARCHAR(16) NOT NULL DEFAULT 'moderate' CHECK (risk_tolerance IN ('conservative', 'moderate', 'aggressive')),
    target_volatility NUMERIC(19, 8) NULL,
    min_sharpe NUMERIC(19, 8) NULL,
    excluded_symbols JSONB NULL,
    preferred_sectors JSONB NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS investments_db.recommendation_run (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    feature_snapshot_id VARCHAR(128) NULL,
    training_cutoff_date DATE NULL,
    confidence_summary NUMERIC(19, 8) NULL,
    disclaimer TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recommendation_run_user_created
    ON investments_db.recommendation_run (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS investments_db.recommendation_item (
    run_id UUID NOT NULL REFERENCES investments_db.recommendation_run(run_id) ON DELETE CASCADE,
    symbol VARCHAR(32) NOT NULL,
    rank INTEGER NOT NULL,
    score NUMERIC(19, 8) NOT NULL,
    expected_return NUMERIC(19, 8) NULL,
    risk_score NUMERIC(19, 8) NULL,
    confidence_low NUMERIC(19, 8) NULL,
    confidence_high NUMERIC(19, 8) NULL,
    rationale JSONB NULL,
    PRIMARY KEY (run_id, symbol)
);
CREATE INDEX IF NOT EXISTS idx_recommendation_item_run_rank
    ON investments_db.recommendation_item (run_id, rank ASC);

CREATE TABLE IF NOT EXISTS investments_db.provider_health (
    provider VARCHAR(32) PRIMARY KEY,
    last_ok_at TIMESTAMPTZ NULL,
    last_error_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    latency_ms NUMERIC(19, 3) NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS investments_db.feature_snapshot (
    feature_snapshot_id VARCHAR(128) PRIMARY KEY,
    user_id INTEGER NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    as_of_date DATE NOT NULL,
    features_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feature_snapshot_user_date
    ON investments_db.feature_snapshot (user_id, as_of_date DESC);
