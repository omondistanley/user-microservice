-- Migration 017: Portfolio health snapshot table
-- Stores daily composite health scores per user for trend tracking

CREATE TABLE IF NOT EXISTS portfolio_health_snapshot (
    snapshot_id    SERIAL PRIMARY KEY,
    user_id        INTEGER NOT NULL,
    snapshot_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    score          SMALLINT NOT NULL CHECK (score >= 0 AND score <= 100),
    tier           VARCHAR(10) NOT NULL DEFAULT 'amber',  -- green | amber | red
    components_json JSONB,
    flags_json      JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolio_health_snapshot_user_date
    ON portfolio_health_snapshot (user_id, snapshot_date);

CREATE INDEX IF NOT EXISTS idx_portfolio_health_snapshot_user
    ON portfolio_health_snapshot (user_id);
