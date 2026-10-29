SELECT driver_code, stint, compound, COUNT(*) AS laps,
       ROUND(REGR_SLOPE(lap_time_seconds, tyre_life_laps), 4) AS raw_slope_s_per_lap,
       ROUND(REGR_SLOPE(lap_time_seconds, tyre_life_laps) + 0.033 * 105.0 / MAX(s.total_laps), 4) AS fuel_corrected_slope,
       ROUND(REGR_R2(lap_time_seconds, tyre_life_laps), 3) AS r2
FROM laps l JOIN sessions s USING (session_id)
WHERE l.session_id = $session_id AND l.is_accurate
  AND NOT l.is_pit_in_lap AND NOT l.is_pit_out_lap AND l.track_status = '1'
GROUP BY driver_code, stint, compound
HAVING COUNT(*) >= 5
ORDER BY compound, fuel_corrected_slope;
