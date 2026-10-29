SELECT l.driver_code, l.lap_number, l.lap_time_seconds, w.track_temp_c, w.air_temp_c
FROM laps l
JOIN LATERAL (
    SELECT ws.track_temp_c, ws.air_temp_c
    FROM weather_samples ws
    WHERE ws.session_id = l.session_id AND ws.session_time_seconds <= l.session_time_seconds
    ORDER BY ws.session_time_seconds DESC
    LIMIT 1
) w ON TRUE
WHERE l.session_id = $session_id AND l.is_accurate
ORDER BY l.lap_number, l.driver_code;
