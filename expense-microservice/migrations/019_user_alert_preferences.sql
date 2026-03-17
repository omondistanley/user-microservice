-- User alert preferences (e.g. low_projected_balance threshold).
-- Run: python run_migration.py migrations/019_user_alert_preferences.sql

CREATE TABLE IF NOT EXISTS expenses_db.user_alert_preference (
    user_id INTEGER NOT NULL,
    alert_type VARCHAR(64) NOT NULL,
    threshold_value NUMERIC(18,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, alert_type)
);

-- Dedup: one low_projected_balance notification per user per day
CREATE TABLE IF NOT EXISTS expenses_db.low_projected_balance_sent (
    user_id INTEGER NOT NULL,
    sent_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, sent_date)
);
