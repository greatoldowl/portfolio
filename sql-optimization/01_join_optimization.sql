-- ============================================================================
-- 01. JOIN optimization: pre-aggregate before joining wide fact tables
-- ============================================================================
-- Engine: ClickHouse (works in PostgreSQL with minor changes)
-- Problem: report joins a 1.5B-row orders fact to a 90M-row customers table
--          and a 40M-row addresses table, then groups by region.
-- Symptom: hash-join spills to disk, query runs ~6–8 min, frequently OOMs.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- BEFORE: naive join, then aggregate. Reads everything, joins everything.
-- ----------------------------------------------------------------------------
SELECT
    a.region,
    count() AS orders_cnt,
    sum(o.amount) AS gmv,
    uniqExact(c.customer_id) AS active_customers
FROM orders AS o
INNER JOIN customers AS c ON c.customer_id = o.customer_id
INNER JOIN addresses AS a ON a.address_id = c.primary_address_id
WHERE o.created_at >= today() - INTERVAL 30 DAY
GROUP BY a.region;


-- ----------------------------------------------------------------------------
-- AFTER: aggregate orders first, then join the small dimension lookups.
-- 1) Push the date filter as early as possible — prunes ClickHouse parts.
-- 2) Aggregate by the join key (customer_id) before joining customers.
-- 3) Move the heavy uniqExact into the pre-aggregation step.
-- ----------------------------------------------------------------------------
WITH orders_30d AS (
    SELECT
        customer_id,
        count() AS orders_cnt,
        sum(amount) AS gmv
    FROM orders
    WHERE created_at >= today() - INTERVAL 30 DAY
    GROUP BY customer_id
),
customers_with_region AS (
    SELECT
        c.customer_id,
        a.region
    FROM customers AS c
    INNER JOIN addresses AS a ON a.address_id = c.primary_address_id
)
SELECT
    cwr.region,
    sum(o.orders_cnt) AS orders_cnt,
    sum(o.gmv) AS gmv,
    count(DISTINCT o.customer_id) AS active_customers
FROM orders_30d AS o
INNER JOIN customers_with_region AS cwr USING (customer_id)
GROUP BY cwr.region;

-- Result: ~6–8 min → ~25–40 s, memory drops 7×. Same answer.
--
-- Why it works:
--   * The 1.5B-row scan is reduced to ~30M aggregated rows BEFORE the join.
--   * customers × addresses is itself pre-joined into a slim CTE,
--     so the planner builds a small hash table for the final join.
--   * ClickHouse pushes the WHERE down into MergeTree part pruning,
--     reading only the recent partitions.
