-- Migration 020: Nudge log table for rate-limiting proactive nudges
CREATE TABLE IF NOT EXISTS nudge_log (
    nudge_id    SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    nudge_type  VARCHAR(64) NOT NULL,
    message     TEXT,
    fired_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_nudge_log_user_type ON nudge_log(user_id, nudge_type, fired_at DESC);
