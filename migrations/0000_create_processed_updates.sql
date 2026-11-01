-- Create the initial Telegram webhook update tracking table.
-- Migration 0001 adds claim ownership and lease fields.

CREATE TABLE IF NOT EXISTS processed_updates (
    update_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL
        CHECK (status IN ('processing', 'processed')),
    claimed_at INTEGER NOT NULL,
    processed_at INTEGER
);