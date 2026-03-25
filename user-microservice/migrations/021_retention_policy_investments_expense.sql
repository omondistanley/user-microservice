-- Extend retention targets to investments + expense profiling-adjacent tables.
-- Purge job: app.jobs.retention_purge (cross-DB when RETENTION_PURGE_CROSS_DB=true).

INSERT INTO users_db.retention_policy (entity, retention_days, is_active) VALUES
    ('inv_recommendation_run', 730, true),
    ('inv_recommendation_digest', 730, true),
    ('inv_portfolio_health_snapshot', 365, true),
    ('inv_nudge_log', 90, true),
    ('exp_anomaly_feedback', 730, true),
    ('exp_classifier_correction', 730, true)
ON CONFLICT (entity) DO NOTHING;
