-- Add ownership and lease fields for safe webhook claim renewal.
-- Existing rows are preserved; active legacy claims receive an equivalent lease.

ALTER TABLE processed_updates
ADD COLUMN claim_token TEXT;

ALTER TABLE processed_updates
ADD COLUMN lease_expires_at INTEGER;

UPDATE processed_updates
SET lease_expires_at = claimed_at + 300
WHERE status = 'processing'
  AND lease_expires_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_processed_updates_status_lease
ON processed_updates (status, lease_expires_at);
