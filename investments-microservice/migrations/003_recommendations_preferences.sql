-- Extend risk_profile for analyst-style recommendations: industry/sector preferences,
-- Sharpe objective, and loss aversion. Supports no-holdings "build portfolio" mode.
ALTER TABLE investments_db.risk_profile
  ADD COLUMN IF NOT EXISTS industry_preferences JSONB DEFAULT '[]';
ALTER TABLE investments_db.risk_profile
  ADD COLUMN IF NOT EXISTS sharpe_objective NUMERIC(19, 8);
ALTER TABLE investments_db.risk_profile
  ADD COLUMN IF NOT EXISTS loss_aversion VARCHAR(32) DEFAULT 'moderate';

COMMENT ON COLUMN investments_db.risk_profile.industry_preferences IS 'Preferred sectors/industries, e.g. ["technology","healthcare","broad_market"]';
COMMENT ON COLUMN investments_db.risk_profile.sharpe_objective IS 'Target Sharpe ratio, engine favors suggestions aligned with this';
COMMENT ON COLUMN investments_db.risk_profile.loss_aversion IS 'moderate|low|high, influences how much we penalize downside risk';
