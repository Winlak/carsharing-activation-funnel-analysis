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
repeat_rides AS (
    SELECT user_id, event_ts AS repeat_ride_ts
    FROM raw_events
    WHERE event_name = 'ride_completed'
),
user_metrics AS (
    SELECT
        b.user_id,
        DATE_TRUNC('month', b.signup_ts) AS signup_cohort,
        b.signup_ts,
        b.first_ride_ts,
        MAX(CASE WHEN b.first_ride_ts <= b.signup_ts + INTERVAL 1 DAY THEN 1 ELSE 0 END) AS activated_d1,
        MAX(CASE WHEN b.first_ride_ts <= b.signup_ts + INTERVAL 7 DAY THEN 1 ELSE 0 END) AS activated_d7,
        MAX(CASE WHEN b.first_ride_ts <= b.signup_ts + INTERVAL 30 DAY THEN 1 ELSE 0 END) AS activated_d30,
        MAX(CASE WHEN r.repeat_ride_ts >= b.first_ride_ts + INTERVAL 1 DAY
                      AND r.repeat_ride_ts < b.first_ride_ts + INTERVAL 2 DAY THEN 1 ELSE 0 END) AS retained_d1,
        MAX(CASE WHEN r.repeat_ride_ts >= b.first_ride_ts + INTERVAL 7 DAY
                      AND r.repeat_ride_ts < b.first_ride_ts + INTERVAL 8 DAY THEN 1 ELSE 0 END) AS retained_d7,
        MAX(CASE WHEN r.repeat_ride_ts >= b.first_ride_ts + INTERVAL 30 DAY
                      AND r.repeat_ride_ts < b.first_ride_ts + INTERVAL 31 DAY THEN 1 ELSE 0 END) AS retained_d30
    FROM user_stages b
    LEFT JOIN repeat_rides r ON b.user_id = r.user_id
    GROUP BY 1, 2, 3, 4
),
cohort_metrics AS (
    SELECT
        signup_cohort,
        COUNT(*) AS registrations,
        SUM(activated_d1) AS activated_d1_users,
        SUM(activated_d7) AS activated_d7_users,
        SUM(activated_d30) AS activated_d30_users,
        COUNT(first_ride_ts) FILTER (WHERE first_ride_ts <= TIMESTAMP '2025-06-29 23:59:00') AS retention_d1_eligible,
        COUNT(first_ride_ts) FILTER (WHERE first_ride_ts <= TIMESTAMP '2025-06-23 23:59:00') AS retention_d7_eligible,
        COUNT(first_ride_ts) FILTER (WHERE first_ride_ts <= TIMESTAMP '2025-05-31 23:59:00') AS retention_d30_eligible,
        SUM(retained_d1) AS retained_d1_users,
        SUM(retained_d7) AS retained_d7_users,
        SUM(retained_d30) AS retained_d30_users
    FROM user_metrics
    GROUP BY 1
)
SELECT
    signup_cohort,
    registrations,
    ROUND(activated_d1_users * 1.0 / registrations, 6) AS activation_d1,
    ROUND(activated_d7_users * 1.0 / registrations, 6) AS activation_d7,
    ROUND(activated_d30_users * 1.0 / registrations, 6) AS activation_d30,
    retention_d1_eligible,
    ROUND(retained_d1_users * 1.0 / NULLIF(retention_d1_eligible, 0), 6) AS retention_d1,
    retention_d7_eligible,
    ROUND(retained_d7_users * 1.0 / NULLIF(retention_d7_eligible, 0), 6) AS retention_d7,
    retention_d30_eligible,
    ROUND(retained_d30_users * 1.0 / NULLIF(retention_d30_eligible, 0), 6) AS retention_d30
FROM cohort_metrics
ORDER BY signup_cohort;
