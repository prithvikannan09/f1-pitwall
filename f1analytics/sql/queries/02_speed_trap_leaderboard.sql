SELECT driver_code, team, MAX(speed_trap_kmh) AS top_speed_kmh
FROM laps
WHERE session_id = $session_id AND speed_trap_kmh IS NOT NULL
GROUP BY driver_code, team
ORDER BY top_speed_kmh DESC;
