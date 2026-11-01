-- Enforce one pending report per user and target.
-- Enforce one pending seller claim per seller and user.
-- Preserve all existing records. No destructive cleanup.

CREATE UNIQUE INDEX IF NOT EXISTS
    idx_reports_user_seller_pending_unique
ON reports(user_id, seller_id)
WHERE status = 'PENDING'
  AND seller_id IS NOT NULL
  AND product_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS
    idx_reports_user_product_pending_unique
ON reports(user_id, product_id)
WHERE status = 'PENDING'
  AND product_id IS NOT NULL
  AND seller_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS
    idx_claims_seller_user_pending_unique
ON seller_claims(seller_id, user_id)
WHERE status = 'PENDING';
