-- Persist deterministic model and quality artifacts per recommendation run.
ALTER TABLE investments_db.recommendation_run
  ADD COLUMN IF NOT EXISTS run_artifacts JSONB;

COMMENT ON COLUMN investments_db.recommendation_run.run_artifacts
  IS 'Model/version/feature contract and quality telemetry captured at run generation time.';
