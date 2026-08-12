-- Overall first-ride funnel. Unit: user; each user is counted once per earliest valid stage.
WITH ranked_stage_events AS (
    SELECT
        user_id,
        event_name,
        event_ts,
        ROW_NUMBER() OVER (PARTITION BY user_id, event_name ORDER BY event_ts, event_id) AS event_rank
    FROM (
        SELECT * REPLACE (CAST(event_ts AS TIMESTAMP) AS event_ts)
        FROM read_csv_auto('data/raw/events.csv', timestampformat='%Y-%m-%dT%H:%M:%SZ')
    )
    WHERE event_name IN ('signup', 'verification', 'payment_method', 'search', 'booking', 'first_ride')
),
first_stage_events AS (
    SELECT user_id, event_name, event_ts
    FROM ranked_stage_events
    WHERE event_rank = 1
),
user_stages AS (
    SELECT
        user_id,
        MAX(CASE WHEN event_name = 'signup' THEN event_ts END) AS signup_ts,
        MAX(CASE WHEN event_name = 'verification' THEN event_ts END) AS verification_ts,
        MAX(CASE WHEN event_name = 'payment_method' THEN event_ts END) AS payment_ts,
        MAX(CASE WHEN event_name = 'search' THEN event_ts END) AS search_ts,
        MAX(CASE WHEN event_name = 'booking' THEN event_ts END) AS booking_ts,
        MAX(CASE WHEN event_name = 'first_ride' THEN event_ts END) AS first_ride_ts
    FROM first_stage_events
    GROUP BY 1
),
valid_progression AS (
    SELECT
        user_id,
        signup_ts,
        CASE WHEN verification_ts >= signup_ts AND verification_ts <= signup_ts + INTERVAL 30 DAY THEN verification_ts END AS verification_ts,
        CASE WHEN payment_ts >= verification_ts AND payment_ts <= signup_ts + INTERVAL 30 DAY THEN payment_ts END AS payment_ts,
        CASE WHEN search_ts >= payment_ts AND search_ts <= signup_ts + INTERVAL 30 DAY THEN search_ts END AS search_ts,
        CASE WHEN booking_ts >= search_ts AND booking_ts <= signup_ts + INTERVAL 30 DAY THEN booking_ts END AS booking_ts,
        CASE WHEN first_ride_ts >= booking_ts AND first_ride_ts <= signup_ts + INTERVAL 30 DAY THEN first_ride_ts END AS first_ride_ts
    FROM user_stages
),
stage_counts AS (
    SELECT 1 AS stage_order, 'signup' AS stage, COUNT(*) AS users FROM valid_progression
    UNION ALL SELECT 2, 'verification', COUNT(verification_ts) FROM valid_progression
    UNION ALL SELECT 3, 'payment_method', COUNT(payment_ts) FROM valid_progression
    UNION ALL SELECT 4, 'search', COUNT(search_ts) FROM valid_progression
    UNION ALL SELECT 5, 'booking', COUNT(booking_ts) FROM valid_progression
    UNION ALL SELECT 6, 'first_ride', COUNT(first_ride_ts) FROM valid_progression
),
with_previous_stage AS (
    SELECT
        *,
        LAG(users) OVER (ORDER BY stage_order) AS previous_stage_users,
        FIRST_VALUE(users) OVER (ORDER BY stage_order) AS signup_users
    FROM stage_counts
)
SELECT
    stage_order,
    stage,
    users,
    ROUND(users * 1.0 / signup_users, 6) AS conversion_from_signup,
    ROUND(users * 1.0 / NULLIF(previous_stage_users, 0), 6) AS conversion_from_previous_stage,
    COALESCE(previous_stage_users - users, 0) AS dropoff_users
FROM with_previous_stage
ORDER BY stage_order;
