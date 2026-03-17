-- Scenario library for stress testing (optional, can also seed in code).
-- Run: python run_migration.py migrations/009_scenarios.sql

CREATE TABLE IF NOT EXISTS investments_db.scenario (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    impacts_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE investments_db.scenario IS 'Historical stress scenarios: asset-class return shocks (e.g. 2008 Crisis, 2022 Rate Hike)';
