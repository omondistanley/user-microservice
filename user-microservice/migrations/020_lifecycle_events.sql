CREATE TABLE IF NOT EXISTS users_db.lifecycle_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users_db."user"(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,  -- 'new_job', 'marriage', 'baby', 'inheritance', 'retirement', 'home_purchase'
    event_date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_events_user_id ON users_db.lifecycle_events(user_id);
