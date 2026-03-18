-- Hosted Link correlation table: link_token -> user_id
-- Used by Plaid SESSION_FINISHED webhook to associate public_token with our user.

CREATE TABLE IF NOT EXISTS expenses_db.plaid_link_token (
    link_token VARCHAR(128) PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plaid_link_token_user_id ON expenses_db.plaid_link_token (user_id);
