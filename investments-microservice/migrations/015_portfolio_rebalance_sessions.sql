-- Track multi-phase rebalance sessions (sell-now then buy-next-day).
-- Rebalance automation creates one session per trigger (auto 4w or manual),
-- then executes in two phases with idempotent guards.

CREATE TABLE IF NOT EXISTS investments_db.portfolio_rebalance_session (
    rebalance_session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id INTEGER NOT NULL,
    household_id UUID NULL,

    -- How this session was triggered.
    trigger_type VARCHAR(32) NOT NULL DEFAULT 'auto_4w', -- auto_4w | manual
    trigger_source VARCHAR(32) NULL, -- e.g. scheduler | api

    -- Planner scenario: scenario 2 (material change) vs scenario 1 (override).
    scenario VARCHAR(32) NOT NULL DEFAULT 'scenario2', -- scenario2 | scenario1 | no_action

    -- Phase state machine.
    phase VARCHAR(32) NOT NULL DEFAULT 'sell_pending', -- sell_pending|sell_done|buy_pending|buy_done|cancelled|no_action_done

    -- Anchor dates to make scheduling idempotent.
    -- sell_date is the date on which sells are intended to be executed.
    -- buy_due_date is the earliest date on which buys are allowed (next trading day).
    sell_date DATE NOT NULL,
    buy_due_date DATE NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Execution timestamps.
    sell_requested_at TIMESTAMPTZ NULL,
    sell_completed_at TIMESTAMPTZ NULL,
    buy_requested_at TIMESTAMPTZ NULL,
    buy_completed_at TIMESTAMPTZ NULL,

    -- Captures planner outputs for notifications + auditing (deterministic rules).
    payload_json JSONB NULL,

    -- Basic guard to avoid re-running the same sell phase.
    -- Example: store order ids from Alpaca or just a hash of planned symbols.
    execution_fingerprint VARCHAR(128) NULL
);

CREATE INDEX IF NOT EXISTS idx_rebalance_session_user_sell_date
    ON investments_db.portfolio_rebalance_session (user_id, sell_date DESC);

CREATE INDEX IF NOT EXISTS idx_rebalance_session_phase
    ON investments_db.portfolio_rebalance_session (phase);

-- Uniqueness: one session per user per sell_date per trigger_type.
-- (Manual triggers that match an existing sell_date should reuse or no-op.)
CREATE UNIQUE INDEX IF NOT EXISTS idx_rebalance_session_unique_user_sell_trigger
    ON investments_db.portfolio_rebalance_session (user_id, sell_date, trigger_type);

COMMENT ON TABLE investments_db.portfolio_rebalance_session IS
    'Multi-phase rebalance automation session state (sell-now then buy-next-day).';

