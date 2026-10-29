SELECT driver_code, lap_number, lap_time_seconds,
       ROUND(lap_time_seconds - MEDIAN(lap_time_seconds) OVER (PARTITION BY lap_number), 3) AS delta_to_median
FROM laps
WHERE session_id = $session_id AND is_accurate
ORDER BY lap_number, delta_to_median;
