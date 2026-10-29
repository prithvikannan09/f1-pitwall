SELECT driver_code, stint, compound,
       COUNT(*) AS laps,
       MIN(tyre_life_laps) AS first_tyre_age,
       MAX(tyre_life_laps) AS last_tyre_age,
       ROUND(AVG(lap_time_seconds), 3) AS avg_lap_s,
       ROUND(STDDEV_SAMP(lap_time_seconds), 3) AS consistency_s
FROM laps
WHERE session_id = $session_id AND is_accurate
  AND NOT is_pit_in_lap AND NOT is_pit_out_lap
GROUP BY driver_code, stint, compound
ORDER BY driver_code, stint;
