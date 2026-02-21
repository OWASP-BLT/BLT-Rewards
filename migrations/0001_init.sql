-- BLT-Rewards D1 Schema
-- Apply with: wrangler d1 execute blt-bacon-db --file=migrations/0001_init.sql

-- Records every BACON transfer
CREATE TABLE IF NOT EXISTS transfers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user_id   TEXT    NOT NULL,
    from_user_name TEXT    NOT NULL,
    to_user_display TEXT   NOT NULL,
    amount         REAL    NOT NULL,
    channel_id     TEXT    NOT NULL,
    created_at     INTEGER NOT NULL
);

-- Users explicitly approved to use /bacon (in addition to workspace admins)
CREATE TABLE IF NOT EXISTS approved_users (
    user_id    TEXT    PRIMARY KEY,
    user_name  TEXT    NOT NULL,
    added_by   TEXT    NOT NULL,   -- Slack user_id of the admin who approved them
    added_at   INTEGER NOT NULL
);

-- Optional: simple key-value config store (for future use)
CREATE TABLE IF NOT EXISTS config (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_transfers_from ON transfers(from_user_id);
CREATE INDEX IF NOT EXISTS idx_transfers_created ON transfers(created_at);
