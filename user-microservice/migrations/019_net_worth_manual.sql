-- Manual net worth assets and liabilities (user-scoped).
CREATE TABLE IF NOT EXISTS users_db.net_worth_asset (
    asset_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    INTEGER NOT NULL,
    name       VARCHAR(255) NOT NULL,
    type       VARCHAR(32) NOT NULL,
    value      NUMERIC(18, 2) NOT NULL DEFAULT 0,
    currency   CHAR(3) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_net_worth_asset_user ON users_db.net_worth_asset (user_id);

CREATE TABLE IF NOT EXISTS users_db.net_worth_liability (
    liability_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      INTEGER NOT NULL,
    name         VARCHAR(255) NOT NULL,
    type         VARCHAR(32) NOT NULL,
    value        NUMERIC(18, 2) NOT NULL DEFAULT 0,
    currency     CHAR(3) NOT NULL DEFAULT 'USD',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_net_worth_liability_user ON users_db.net_worth_liability (user_id);
