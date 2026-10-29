SELECT l.driver_code, l.lap_number, l.lap_time_seconds,
       MAX(t.speed_kmh) AS top_speed_kmh,
       ROUND(100.0 * AVG(CASE WHEN t.throttle_pct >= 98 THEN 1 ELSE 0 END), 1) AS full_throttle_pct,
       ROUND(100.0 * AVG(CASE WHEN t.brake_active THEN 1 ELSE 0 END), 1) AS braking_pct
FROM telemetry_samples t JOIN laps l USING (lap_id)
WHERE l.session_id = $session_id
GROUP BY l.driver_code, l.lap_number, l.lap_time_seconds
ORDER BY l.lap_time_seconds;
