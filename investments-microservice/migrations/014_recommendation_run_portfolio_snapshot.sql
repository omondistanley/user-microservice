-- Persist portfolio metrics JSON on each recommendation run for /latest UI and auditing.
ALTER TABLE investments_db.recommendation_run
  ADD COLUMN IF NOT EXISTS portfolio_snapshot JSONB;

COMMENT ON COLUMN investments_db.recommendation_run.portfolio_snapshot IS 'Portfolio metrics at run time (value, risk, concentration, holdings_top, etc.).';
