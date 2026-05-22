-- ============================================================================
-- 04. PostgreSQL: indexes that actually get used + EXPLAIN workflow
-- ============================================================================
-- Rules of thumb I lean on when a slow query lands in the backlog:
--   1. Look at the planner first: EXPLAIN (ANALYZE, BUFFERS) <query>.
--   2. Index the columns in WHERE / JOIN, not in SELECT.
--   3. Composite index column order = filter selectivity, descending.
--   4. Use partial indexes for hot-but-rare conditions.
--   5. BRIN for append-only time-series, B-tree for everything else.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- Diagnose: a typical "why is this slow" check
-- ----------------------------------------------------------------------------
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT u.id, u.email, count(o.id) AS orders_cnt
FROM users u
LEFT JOIN orders o
       ON o.user_id = u.id
      AND o.created_at >= now() - INTERVAL '30 days'
WHERE u.status = 'active'
  AND u.country = 'RU'
GROUP BY u.id, u.email
ORDER BY orders_cnt DESC
LIMIT 100;
-- Look for: Seq Scan on big tables, Hash Join with high "Buckets x Batches",
--           and "Rows Removed by Filter" much larger than "Rows".


-- ----------------------------------------------------------------------------
-- Composite + partial indexes for the query above
-- ----------------------------------------------------------------------------
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_active_country
    ON users (country)
    INCLUDE (id, email)
    WHERE status = 'active';

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_user_recent
    ON orders (user_id, created_at DESC);

-- INCLUDE turns the index into a covering one for the SELECT list —
-- the planner can do an Index-Only Scan and skip the heap entirely.


-- ----------------------------------------------------------------------------
-- BRIN for huge append-only event tables
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS brin_events_created_at
    ON events USING BRIN (created_at) WITH (pages_per_range = 32);
-- Tiny (~MB instead of GB), great for date-range filters when data is
-- physically clustered by time.


-- ----------------------------------------------------------------------------
-- Things I look for in EXPLAIN ANALYZE output
-- ----------------------------------------------------------------------------
--   * "actual rows" >> "rows" estimate → stale stats, run ANALYZE.
--   * Nested Loop with high outer rows → missing index on inner table.
--   * Sort Method: external merge → work_mem too low.
--   * Buffers: shared read=...  → cold cache, repeat the query to compare.
--   * Lossy bitmap heap scans → increase work_mem or rewrite predicate.


-- ----------------------------------------------------------------------------
-- Keep statistics fresh on hot tables
-- ----------------------------------------------------------------------------
ALTER TABLE orders SET (autovacuum_analyze_scale_factor = 0.02);
ALTER TABLE users  SET (autovacuum_analyze_scale_factor = 0.02);
