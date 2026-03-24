-- Migration 027: Global idempotency key table for all write endpoints
-- Any endpoint that accepts an Idempotency-Key header stores the result here
-- so duplicate requests within 24 h return the cached response.
--
-- Usage pattern:
--   1. Compute key = SHA-256(user_id || idempotency_key_header)
--   2. SELECT * WHERE key = <hash> AND created_at > now() - interval '24 hours'
--   3. If found → return cached_response (skip business logic)
--   4. If not found → run logic, INSERT result, return it

BEGIN;

CREATE TABLE IF NOT EXISTS expenses_db.global_idempotency_key (
    key             TEXT        PRIMARY KEY,   -- SHA-256 hex of (user_id + client key)
    user_id         INTEGER     NOT NULL,
    endpoint        TEXT        NOT NULL,      -- e.g. 'POST /api/v1/expenses'
    status_code     SMALLINT    NOT NULL DEFAULT 200,
    cached_response JSONB       NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '24 hours'
);

CREATE INDEX IF NOT EXISTS idx_global_idempotency_user
    ON expenses_db.global_idempotency_key (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_global_idempotency_expires
    ON expenses_db.global_idempotency_key (expires_at);

-- Cleanup function: call via pg_cron or a periodic task to prune expired keys
-- SELECT expenses_db.purge_expired_idempotency_keys();
CREATE OR REPLACE FUNCTION expenses_db.purge_expired_idempotency_keys()
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE
    deleted INTEGER;
BEGIN
    DELETE FROM expenses_db.global_idempotency_key WHERE expires_at < now();
    GET DIAGNOSTICS deleted = ROW_COUNT;
    RETURN deleted;
END;
$$;

COMMIT;
