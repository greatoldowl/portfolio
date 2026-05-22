-- ============================================================================
-- 03. ClickHouse: partitioning + sort order + data-skipping index
-- ============================================================================
-- Common mistake: a single PARTITION BY toDate(event_time) on a high-cardinality
-- table produces millions of small parts and slow merges.
-- Goal: balance part pruning with merge cost.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- BEFORE: too granular partitioning, no skip index, sort order doesn't match
--         the most frequent filter.
-- ----------------------------------------------------------------------------
CREATE TABLE events_v1
(
    event_time DateTime,
    user_id    UInt64,
    event_type LowCardinality(String),
    country    LowCardinality(String),
    payload    String
)
ENGINE = MergeTree
PARTITION BY toDate(event_time)            -- daily → thousands of parts
ORDER BY event_time;                       -- bad for per-user queries


-- ----------------------------------------------------------------------------
-- AFTER: monthly partition, sort by the typical filter combo,
--        skip index for the secondary filter.
-- ----------------------------------------------------------------------------
CREATE TABLE events_v2
(
    event_time DateTime,
    user_id    UInt64,
    event_type LowCardinality(String),
    country    LowCardinality(String),
    payload    String,

    INDEX idx_country country TYPE bloom_filter(0.01) GRANULARITY 4,
    INDEX idx_event_type event_type TYPE set(64) GRANULARITY 4
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (user_id, event_time)
SETTINGS index_granularity = 8192;

-- Query benefiting from the new layout
SELECT
    user_id,
    count() AS events_cnt,
    countIf(event_type = 'purchase') AS purchases
FROM events_v2
WHERE event_time >= now() - INTERVAL 14 DAY
  AND country = 'RU'
  AND user_id IN (
      SELECT user_id FROM target_audience_users
  )
GROUP BY user_id;

-- Diagnostics: confirm part pruning + index usage
EXPLAIN indexes = 1
SELECT user_id FROM events_v2
WHERE event_time >= now() - INTERVAL 14 DAY AND country = 'RU';


-- ----------------------------------------------------------------------------
-- Migration pattern: backfill in chunks to avoid huge merges
-- ----------------------------------------------------------------------------
INSERT INTO events_v2
SELECT event_time, user_id, event_type, country, payload
FROM events_v1
WHERE event_time >= toDateTime('2025-01-01')
  AND event_time <  toDateTime('2025-02-01');
-- repeat per month, monitor system.merges between batches.


-- ----------------------------------------------------------------------------
-- Materialized view to keep a thin pre-aggregate hot
-- ----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW events_daily_mv
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(event_date)
ORDER BY (event_date, country, event_type)
AS
SELECT
    toDate(event_time) AS event_date,
    country,
    event_type,
    count() AS events_cnt,
    uniqState(user_id) AS users_state
FROM events_v2
GROUP BY event_date, country, event_type;

-- Reading from the MV is ~50–200× faster than scanning raw events for daily
-- KPI dashboards in Superset / DataLens.
