-- Link Gmail Pub/Sub notifications (emailAddress) to app user_id for multi-tenant webhooks.

BEGIN;

ALTER TABLE expenses_db.gmail_oauth_token
    ADD COLUMN IF NOT EXISTS google_account_email VARCHAR(320);

CREATE UNIQUE INDEX IF NOT EXISTS uq_gmail_oauth_google_email_lower
    ON expenses_db.gmail_oauth_token (lower(google_account_email::text))
    WHERE google_account_email IS NOT NULL;

COMMIT;
