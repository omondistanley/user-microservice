-- Opt-in for using savings, goals, expenses, and budget to personalize recommendations.
-- When false or null, recommendation engine does not fetch or use finance context.
ALTER TABLE investments_db.risk_profile
  ADD COLUMN IF NOT EXISTS use_finance_data_for_recommendations BOOLEAN DEFAULT false;

COMMENT ON COLUMN investments_db.risk_profile.use_finance_data_for_recommendations IS 'When true, recommendations use income/expenses/goals/budget for soft scoring and narrative. User-controlled.';
