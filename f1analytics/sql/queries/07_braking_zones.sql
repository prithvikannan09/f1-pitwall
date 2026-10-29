SELECT driver_code, ROUND(distance_meters) AS brake_point_m, speed_kmh AS entry_speed_kmh
FROM (
    SELECT l.driver_code, t.distance_meters, t.speed_kmh, t.brake_active,
           LAG(t.brake_active) OVER (PARTITION BY t.lap_id ORDER BY t.distance_meters) AS prev_brake
    FROM telemetry_samples t JOIN laps l USING (lap_id)
    WHERE l.session_id = $session_id
) x
WHERE brake_active AND NOT COALESCE(prev_brake, FALSE) AND speed_kmh > 150
ORDER BY driver_code, brake_point_m;
