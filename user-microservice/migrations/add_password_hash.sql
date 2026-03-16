-- PostgreSQL: ensure schema exists, then add password_hash for auth.
-- Run while connected to your database (e.g. users_db).
-- Existing rows get NULL, new registrations will store bcrypt hash.
CREATE SCHEMA IF NOT EXISTS users_db;
-- If table users_db.user does not exist, create it first, then:
ALTER TABLE users_db."user" ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255) NULL;
