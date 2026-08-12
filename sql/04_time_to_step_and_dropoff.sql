-- Time-to-step and drop-off. Time is calculated only for users who reached both adjacent steps.
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
    SELECT user_id, event_name, event_ts FROM ranked_stage_events WHERE event_rank = 1
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
