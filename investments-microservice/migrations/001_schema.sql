-- Investments microservice schema: holdings (stocks/ETFs) for tracking.
-- Run: python run_migration.py migrations/001_schema.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS investments_db;

-- Holdings: user positions (symbol, quantity, average cost). Optional household scope.
CREATE TABLE IF NOT EXISTS investments_db.holding (
    holding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    household_id UUID NULL,
    symbol VARCHAR(32) NOT NULL,
    quantity NUMERIC(19, 6) NOT NULL CHECK (quantity > 0),
    avg_cost NUMERIC(19, 4) NOT NULL CHECK (avg_cost >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    exchange VARCHAR(32) NULL,
    notes VARCHAR(512) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_holding_user ON investments_db.holding (user_id);
CREATE INDEX IF NOT EXISTS idx_holding_user_household ON investments_db.holding (user_id, household_id);
CREATE INDEX IF NOT EXISTS idx_holding_symbol ON investments_db.holding (user_id, symbol);

-- Market quotes: latest price per symbol/provider.
CREATE TABLE IF NOT EXISTS investments_db.market_quote (
    quote_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(32) NOT NULL,
    provider VARCHAR(32) NOT NULL,
    price NUMERIC(19, 8) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'USD',
    as_of TIMESTAMPTZ NOT NULL,
    freshness_seconds INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_market_quote_symbol_provider
    ON investments_db.market_quote (symbol, provider);

-- Price bars: OHLCV time-series.
CREATE TABLE IF NOT EXISTS investments_db.price_bar (
    bar_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(32) NOT NULL,
    interval VARCHAR(16) NOT NULL, -- e.g. 1m, 5m, 1d
    period_start TIMESTAMPTZ NOT NULL,
    open NUMERIC(19, 8) NOT NULL,
    high NUMERIC(19, 8) NOT NULL,
    low NUMERIC(19, 8) NOT NULL,
    close NUMERIC(19, 8) NOT NULL,
    volume NUMERIC(24, 4) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_price_bar_symbol_interval_start
    ON investments_db.price_bar (symbol, interval, period_start);

-- Daily portfolio snapshots: aggregated valuations per user.
CREATE TABLE IF NOT EXISTS investments_db.portfolio_snapshot (
    snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,
    total_value NUMERIC(19, 4) NOT NULL,
    total_cost_basis NUMERIC(19, 4) NOT NULL,
    unrealized_pl NUMERIC(19, 4) NOT NULL,
    realized_pl NUMERIC(19, 4) NOT NULL DEFAULT 0,
    volatility_30d NUMERIC(19, 8),
    max_drawdown_90d NUMERIC(19, 8),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolio_snapshot_user_date
    ON investments_db.portfolio_snapshot (user_id, snapshot_date);

-- User risk profile and preferences.
CREATE TABLE IF NOT EXISTS investments_db.risk_profile (
    user_id INTEGER PRIMARY KEY,
    risk_tolerance VARCHAR(32) NOT NULL, -- e.g. conservative, balanced, aggressive
    horizon_years INTEGER,
    liquidity_needs VARCHAR(128),
    target_volatility NUMERIC(19, 8),
    constraints_json JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Recommendation runs: metadata for each run.
CREATE TABLE IF NOT EXISTS investments_db.recommendation_run (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    model_version VARCHAR(64),
    feature_snapshot_id UUID,
    training_cutoff_date DATE,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_recommendation_run_user_created
    ON investments_db.recommendation_run (user_id, created_at DESC);

-- Individual recommendation items within a run.
CREATE TABLE IF NOT EXISTS investments_db.recommendation_item (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES investments_db.recommendation_run(run_id) ON DELETE CASCADE,
    symbol VARCHAR(32) NOT NULL,
    score NUMERIC(19, 8) NOT NULL,
    confidence NUMERIC(19, 8),
    explanation_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recommendation_item_run
    ON investments_db.recommendation_item (run_id);

-- Provider health/telemetry.
CREATE TABLE IF NOT EXISTS investments_db.provider_health (
    provider VARCHAR(32) PRIMARY KEY,
    status VARCHAR(16) NOT NULL, -- e.g. healthy, degraded, down
    latency_ms NUMERIC(10, 2),
    error_rate NUMERIC(5, 4),
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB
);

