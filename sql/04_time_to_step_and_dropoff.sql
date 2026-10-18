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
step_times AS (
    SELECT 2 AS stage_order, 'signup → verification' AS transition,
           DATE_DIFF('minute', signup_ts, verification_ts) / 60.0 AS hours_to_step
    FROM user_stages WHERE verification_ts >= signup_ts AND verification_ts <= signup_ts + INTERVAL 30 DAY
    UNION ALL
    SELECT 3, 'verification → payment_method', DATE_DIFF('minute', verification_ts, payment_ts) / 60.0
    FROM user_stages WHERE payment_ts >= verification_ts AND payment_ts <= signup_ts + INTERVAL 30 DAY
    UNION ALL
    SELECT 4, 'payment_method → search', DATE_DIFF('minute', payment_ts, search_ts) / 60.0
    FROM user_stages WHERE search_ts >= payment_ts AND search_ts <= signup_ts + INTERVAL 30 DAY
    UNION ALL
    SELECT 5, 'search → booking', DATE_DIFF('minute', search_ts, booking_ts) / 60.0
    FROM user_stages WHERE booking_ts >= search_ts AND booking_ts <= signup_ts + INTERVAL 30 DAY
    UNION ALL
    SELECT 6, 'booking → first_ride', DATE_DIFF('minute', booking_ts, first_ride_ts) / 60.0
    FROM user_stages WHERE first_ride_ts >= booking_ts AND first_ride_ts <= signup_ts + INTERVAL 30 DAY
),
summary AS (
    SELECT
        stage_order,
        transition,
        COUNT(*) AS users_reaching_both_steps,
        QUANTILE_CONT(hours_to_step, 0.50) AS p50_hours,
        QUANTILE_CONT(hours_to_step, 0.90) AS p90_hours
    FROM step_times
    GROUP BY 1, 2
)
SELECT stage_order, transition, users_reaching_both_steps,
       ROUND(p50_hours, 2) AS p50_hours, ROUND(p90_hours, 2) AS p90_hours
FROM summary
ORDER BY stage_order;
