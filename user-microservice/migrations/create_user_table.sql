-- Create users_db schema and user table expected by UserResource.
-- Run while connected to your database (e.g. psql -d users_db -f migrations/create_user_table.sql).
CREATE SCHEMA IF NOT EXISTS users_db;

CREATE TABLE IF NOT EXISTS users_db."user" (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    password_hash VARCHAR(255),
    created_at TIMESTAMP,
    modified_at TIMESTAMP
);

-- Ensure password_hash exists if table was created without it
ALTER TABLE users_db."user" ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255) NULL;
ALTER TABLE users_db."user" ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NULL;
ALTER TABLE users_db."user" ADD COLUMN IF NOT EXISTS modified_at TIMESTAMP NULL;
