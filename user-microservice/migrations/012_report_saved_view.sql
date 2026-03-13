-- Phase 4: Saved report views (filter payload per user).
-- Run as part of user migrations.

CREATE TABLE IF NOT EXISTS users_db.report_saved_view (
    view_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_report_saved_view_user FOREIGN KEY (user_id) REFERENCES users_db."user"(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_report_saved_view_user ON users_db.report_saved_view (user_id);
