-- Migration 018: Recommendation digest table
-- Stores weekly investment digests for users

CREATE TABLE IF NOT EXISTS recommendation_digest (
    digest_id       SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    week_start_date DATE NOT NULL,
    headline        TEXT,
    body_text       TEXT,
    portfolio_score SMALLINT,
    surplus_amount  NUMERIC(19,4),
    digest_json     JSONB,
    delivered       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rec_digest_user_week
    ON recommendation_digest (user_id, week_start_date);

CREATE INDEX IF NOT EXISTS idx_rec_digest_user
    ON recommendation_digest (user_id);
