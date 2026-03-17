-- Dedup: one no_income_logged notification per user per month.
-- Run: python run_migration.py migrations/018_no_income_notification_dedup.sql

CREATE TABLE IF NOT EXISTS expenses_db.no_income_notification_sent (
    user_id INTEGER NOT NULL,
    year_month CHAR(7) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, year_month)
);
