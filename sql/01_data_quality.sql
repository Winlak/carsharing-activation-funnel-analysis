-- Data-quality checks at event grain. Expected result: all issue values are zero.
WITH raw AS (
    SELECT * REPLACE (CAST(event_ts AS TIMESTAMP) AS event_ts)
    FROM read_csv_auto('data/raw/events.csv', timestampformat='%Y-%m-%dT%H:%M:%SZ')
),
ranked_events AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY event_ts, user_id) AS event_id_rank
    FROM raw
),
first_stage AS (
    SELECT
        user_id,
        event_name,
        MIN(event_ts) AS first_ts
    FROM raw
    WHERE event_name IN ('signup', 'verification', 'payment_method', 'search', 'booking', 'first_ride')
    GROUP BY 1, 2
),
stage_pivot AS (
    SELECT
        user_id,
        MAX(CASE WHEN event_name = 'signup' THEN first_ts END) AS signup_ts,
        MAX(CASE WHEN event_name = 'verification' THEN first_ts END) AS verification_ts,
        MAX(CASE WHEN event_name = 'payment_method' THEN first_ts END) AS payment_ts,
        MAX(CASE WHEN event_name = 'search' THEN first_ts END) AS search_ts,
        MAX(CASE WHEN event_name = 'booking' THEN first_ts END) AS booking_ts,
        MAX(CASE WHEN event_name = 'first_ride' THEN first_ts END) AS first_ride_ts
    FROM first_stage
    GROUP BY 1
),
order_violations AS (
    SELECT COUNT(*) AS issue_value
    FROM stage_pivot
    WHERE (verification_ts IS NOT NULL AND (signup_ts IS NULL OR verification_ts < signup_ts))
       OR (payment_ts IS NOT NULL AND (verification_ts IS NULL OR payment_ts < verification_ts))
       OR (search_ts IS NOT NULL AND (payment_ts IS NULL OR search_ts < payment_ts))
       OR (booking_ts IS NOT NULL AND (search_ts IS NULL OR booking_ts < search_ts))
       OR (first_ride_ts IS NOT NULL AND (booking_ts IS NULL OR first_ride_ts < booking_ts))
)
SELECT 'duplicate_event_id' AS check_name, COUNT(*)::BIGINT AS issue_value
FROM ranked_events
WHERE event_id_rank > 1
UNION ALL
SELECT 'missing_required_field', COUNT(*)::BIGINT
FROM raw
WHERE event_id IS NULL OR user_id IS NULL OR event_name IS NULL OR event_ts IS NULL
UNION ALL
SELECT 'invalid_event_name', COUNT(*)::BIGINT
FROM raw
WHERE event_name NOT IN ('signup', 'verification', 'payment_method', 'search', 'booking', 'first_ride', 'ride_completed')
UNION ALL
SELECT 'future_of_analysis_window', COUNT(*)::BIGINT
FROM raw
WHERE event_ts > TIMESTAMP '2025-06-30 23:59:00'
UNION ALL
SELECT 'missing_signup', COUNT(*)::BIGINT
FROM stage_pivot WHERE signup_ts IS NULL
UNION ALL
SELECT 'stage_order_violation', issue_value::BIGINT
FROM order_violations
ORDER BY 1;
