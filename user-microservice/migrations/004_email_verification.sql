-- Email verification: optional verified-at timestamp and token for verification link.
-- Run: python run_migration.py migrations/004_email_verification.sql
ALTER TABLE users_db."user" ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ NULL;
ALTER TABLE users_db."user" ADD COLUMN IF NOT EXISTS verification_token_hash VARCHAR(64) NULL;
ALTER TABLE users_db."user" ADD COLUMN IF NOT EXISTS verification_token_expires_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS idx_user_verification_token ON users_db."user" (verification_token_hash) WHERE verification_token_hash IS NOT NULL;
