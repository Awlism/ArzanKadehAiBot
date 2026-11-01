-- Persist one-time Telegram webhook configuration state.
-- A lease prevents overlapping scheduled invocations from configuring twice.

CREATE TABLE IF NOT EXISTS worker_webhook_setup (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'processing', 'configured')),
    claim_token TEXT,
    lease_expires_at INTEGER,
    configured_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO worker_webhook_setup (
    id,
    status,
    claim_token,
    lease_expires_at,
    configured_at
)
VALUES (
    1,
    'pending',
    NULL,
    NULL,
    NULL
);