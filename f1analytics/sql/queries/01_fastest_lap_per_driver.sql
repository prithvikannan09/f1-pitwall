SELECT driver_code, team, lap_number, lap_time_seconds, compound,
       lap_time_seconds - MIN(lap_time_seconds) OVER () AS gap_to_fastest
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY driver_code ORDER BY lap_time_seconds) AS rn
    FROM laps
    WHERE session_id = $session_id AND lap_time_seconds IS NOT NULL AND is_accurate
) ranked
WHERE rn = 1
ORDER BY lap_time_seconds;
