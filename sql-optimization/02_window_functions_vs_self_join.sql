-- ============================================================================
-- 02. Replace correlated self-join with a window function
-- ============================================================================
-- Engine: PostgreSQL / ClickHouse
-- Problem: "for each user, get their previous order to compute days_between"
--          written as a correlated self-join — O(N²) per partition.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- BEFORE: correlated subquery / self-join. Scans orders once per row.
-- ----------------------------------------------------------------------------
SELECT
    o.order_id,
    o.user_id,
    o.created_at,
    (
        SELECT max(p.created_at)
        FROM orders p
        WHERE p.user_id = o.user_id
          AND p.created_at < o.created_at
    ) AS prev_order_at,
    o.created_at - (
        SELECT max(p.created_at)
        FROM orders p
        WHERE p.user_id = o.user_id
          AND p.created_at < o.created_at
    ) AS days_since_prev
FROM orders o
WHERE o.created_at >= now() - INTERVAL '90 days';

-- ----------------------------------------------------------------------------
-- AFTER: LAG() over a partition. One pass, sort once.
-- ----------------------------------------------------------------------------
SELECT
    order_id,
    user_id,
    created_at,
    LAG(created_at) OVER w AS prev_order_at,
    created_at - LAG(created_at) OVER w AS days_since_prev
FROM orders
WHERE created_at >= now() - INTERVAL '90 days'
WINDOW w AS (PARTITION BY user_id ORDER BY created_at);

-- Result on a 200M-row orders table: ~14 min → ~50 s.
-- Index used: (user_id, created_at).
--
-- Bonus: the same window can produce multiple lag/lead metrics without
--        adding new scans.


-- ============================================================================
-- Cohort retention with a single ROW_NUMBER pass (no self-join)
-- ============================================================================
WITH first_order AS (
    SELECT
        user_id,
        min(created_at)::date AS cohort_day
    FROM orders
    GROUP BY user_id
),
orders_with_cohort AS (
    SELECT
        o.user_id,
        f.cohort_day,
        (o.created_at::date - f.cohort_day) AS day_offset
    FROM orders o
    JOIN first_order f USING (user_id)
)
SELECT
    cohort_day,
    day_offset,
    count(DISTINCT user_id) AS active_users
FROM orders_with_cohort
WHERE day_offset BETWEEN 0 AND 30
GROUP BY cohort_day, day_offset
ORDER BY cohort_day, day_offset;
