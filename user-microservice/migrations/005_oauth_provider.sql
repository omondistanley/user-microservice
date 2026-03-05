-- OAuth: provider and provider subject for Google/Apple sign-in.
-- Run: python run_migration.py migrations/005_oauth_provider.sql
ALTER TABLE users_db."user" ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(32) NULL;
ALTER TABLE users_db."user" ADD COLUMN IF NOT EXISTS auth_provider_sub VARCHAR(255) NULL;

-- One provider account maps to one local user (unique when both set)
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_auth_provider_sub
ON users_db."user" (auth_provider, auth_provider_sub)
WHERE auth_provider IS NOT NULL AND auth_provider_sub IS NOT NULL;
