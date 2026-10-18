-- Registered users: [2025-01-01, 2025-05-01), UTC; ordered steps within 30 days.
WITH raw_events AS (
    SELECT * REPLACE (CAST(event_ts AS TIMESTAMP) AS event_ts)
    FROM read_csv_auto('data/raw/events.csv', timestampformat='%Y-%m-%dT%H:%M:%SZ')
),
ranked_stage_events AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id, event_name ORDER BY event_ts, event_id) AS event_rank
    FROM raw_events
    WHERE event_name IN ('signup', 'verification', 'payment_method', 'search', 'booking', 'first_ride')
),
raw_user_stages AS (
    SELECT user_id,
        MAX(CASE WHEN event_name = 'signup' THEN acquisition_channel END) AS acquisition_channel,
        MAX(CASE WHEN event_name = 'signup' THEN platform END) AS platform,
        MAX(CASE WHEN event_name = 'signup' THEN city END) AS city,
        MAX(CASE WHEN event_name = 'signup' THEN event_ts END) AS signup_ts,
        MAX(CASE WHEN event_name = 'verification' THEN event_ts END) AS verification_ts,
        MAX(CASE WHEN event_name = 'payment_method' THEN event_ts END) AS payment_ts,
        MAX(CASE WHEN event_name = 'search' THEN event_ts END) AS search_ts,
        MAX(CASE WHEN event_name = 'booking' THEN event_ts END) AS booking_ts,
        MAX(CASE WHEN event_name = 'first_ride' THEN event_ts END) AS first_ride_ts
    FROM ranked_stage_events WHERE event_rank = 1
    GROUP BY user_id
),
cohort AS (
    SELECT * FROM raw_user_stages
    WHERE signup_ts >= TIMESTAMP '2025-01-01'
      AND signup_ts < TIMESTAMP '2025-05-01'
),
ordered_stages AS (
    SELECT *,
        CASE WHEN verification_ts >= signup_ts AND verification_ts <= signup_ts + INTERVAL 30 DAY THEN verification_ts END AS valid_verification_ts,
        CASE WHEN payment_ts >= valid_verification_ts AND payment_ts <= signup_ts + INTERVAL 30 DAY THEN payment_ts END AS valid_payment_ts,
        CASE WHEN search_ts >= valid_payment_ts AND search_ts <= signup_ts + INTERVAL 30 DAY THEN search_ts END AS valid_search_ts,
        CASE WHEN booking_ts >= valid_search_ts AND booking_ts <= signup_ts + INTERVAL 30 DAY THEN booking_ts END AS valid_booking_ts,
        CASE WHEN first_ride_ts >= valid_booking_ts AND first_ride_ts <= signup_ts + INTERVAL 30 DAY THEN first_ride_ts END AS valid_first_ride_ts
    FROM cohort
),
user_stages AS (
    SELECT user_id, signup_ts, acquisition_channel, platform, city,
        valid_verification_ts AS verification_ts,
        valid_payment_ts AS payment_ts,
        valid_search_ts AS search_ts,
        valid_booking_ts AS booking_ts,
        valid_first_ride_ts AS first_ride_ts
    FROM ordered_stages
),
stage_counts AS (
    SELECT 1 AS stage_order, 'signup' AS stage, COUNT(*) AS users FROM user_stages
    UNION ALL SELECT 2, 'verification', COUNT(verification_ts) FROM user_stages
    UNION ALL SELECT 3, 'payment_method', COUNT(payment_ts) FROM user_stages
    UNION ALL SELECT 4, 'search', COUNT(search_ts) FROM user_stages
    UNION ALL SELECT 5, 'booking', COUNT(booking_ts) FROM user_stages
    UNION ALL SELECT 6, 'first_ride', COUNT(first_ride_ts) FROM user_stages
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
    ROUND(users * 1.0 / NULLIF(signup_users, 0), 6) AS conversion_from_signup,
    ROUND(users * 1.0 / NULLIF(previous_stage_users, 0), 6) AS conversion_from_previous_stage,
    COALESCE(previous_stage_users - users, 0) AS dropoff_users
FROM with_previous_stage
ORDER BY stage_order;
