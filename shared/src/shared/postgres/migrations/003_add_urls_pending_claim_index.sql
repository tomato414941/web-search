-- pg_only: true
-- Add composite index for efficient pending URL claiming with SKIP LOCKED.
-- The index covers status filtering + priority ordering + created_at for aging.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_urls_pending_claim
    ON urls (status, priority DESC, created_at)
    WHERE status = 'pending';
