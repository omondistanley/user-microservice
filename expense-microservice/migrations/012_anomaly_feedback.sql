-- Phase 4: Anomaly feedback (ignore/valid) for insights.
-- Run: python run_migration.py migrations/012_anomaly_feedback.sql

CREATE TABLE IF NOT EXISTS expenses_db.anomaly_feedback (
    expense_id UUID NOT NULL,
    user_id INTEGER NOT NULL,
    feedback VARCHAR(16) NOT NULL CHECK (feedback IN ('valid', 'ignore')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (expense_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_anomaly_feedback_user ON expenses_db.anomaly_feedback (user_id);
