from datetime import datetime, timezone

import pandas as pd

from f1analytics.analysis.laps import seconds


def _int_or_none(series):
    return pd.to_numeric(series, errors="coerce").round().astype("Int64")


def laps_rows(sd):
    laps = sd.laps
    return pd.DataFrame({
        "session_id": sd.meta["session_id"],
        "driver_number": laps["DriverNumber"].fillna(laps["Driver"]).astype(str),
        "lap_number": _int_or_none(laps["LapNumber"]),
        "lap_time_seconds": seconds(laps["LapTime"]),
        "sector1_seconds": seconds(laps["Sector1Time"]),
        "sector2_seconds": seconds(laps["Sector2Time"]),
        "sector3_seconds": seconds(laps["Sector3Time"]),
        "compound": laps["Compound"].astype("object"),
        "tyre_life_laps": _int_or_none(laps["TyreLife"]),
        "is_pit_out_lap": laps["PitOutTime"].notna(),
        "is_pit_in_lap": laps["PitInTime"].notna(),
        "driver_code": laps["Driver"].astype(str),
        "team": laps["Team"].astype("object"),
        "stint": _int_or_none(laps["Stint"]),
        "track_status": laps["TrackStatus"].astype("object"),
        "speed_trap_kmh": pd.to_numeric(laps["SpeedST"], errors="coerce"),
        "is_accurate": laps["IsAccurate"].astype(bool),
        "session_time_seconds": seconds(laps["Time"]),
        "position": _int_or_none(laps["Position"]),
    }).dropna(subset=["lap_number"])


def weather_rows(sd):
    w = sd.weather
    if w is None or w.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "session_id": sd.meta["session_id"],
        "session_time_seconds": seconds(w["Time"]),
        "air_temp_c": w["AirTemp"],
        "track_temp_c": w["TrackTemp"],
        "humidity_pct": w["Humidity"],
        "pressure_hpa": w["Pressure"],
        "rainfall": w["Rainfall"].astype(bool),
        "wind_speed_ms": w["WindSpeed"],
    }).dropna(subset=["session_time_seconds"])


def session_exists(con, session_id):
    return con.execute("SELECT COUNT(*) FROM sessions WHERE session_id = ?", [session_id]).fetchall()[0][0] > 0


def delete_session(con, session_id):
    con.execute("DELETE FROM telemetry_samples WHERE lap_id IN (SELECT lap_id FROM laps WHERE session_id = ?)", [session_id])
    con.execute("DELETE FROM weather_samples WHERE session_id = ?", [session_id])
    con.execute("DELETE FROM laps WHERE session_id = ?", [session_id])
    con.execute("DELETE FROM sessions WHERE session_id = ?", [session_id])


def _telemetry_targets(sd, mode):
    if mode == "none" or sd._telemetry_fn is None:
        return []
    if mode == "all":
        return [(d, int(n)) for d, n in sd.laps[["Driver", "LapNumber"]].dropna().itertuples(index=False)]
    return [(d, -1) for d in sd.drivers]


def _telemetry_frames(sd, mode):
    frames = []
    for driver, lap in _telemetry_targets(sd, mode):
        try:
            tel = sd.telemetry(driver, lap)
        except Exception:
            continue
        if lap == -1:
            rows = sd.laps[sd.laps["Driver"] == driver]
            valid = rows[rows["LapTime"].notna() & rows["IsAccurate"].astype(bool)]
            if valid.empty:
                valid = rows[rows["LapTime"].notna()]
            if valid.empty:
                continue
            lap = int(valid.loc[valid["LapTime"].idxmin(), "LapNumber"])
        frames.append(pd.DataFrame({
            "driver_code": driver,
            "lap_number": lap,
            "timestamp_utc": pd.to_datetime(tel["Date"]).dt.tz_localize(None) if getattr(tel["Date"].dt, "tz", None) else pd.to_datetime(tel["Date"]),
            "distance_meters": tel["Distance"].astype(float),
            "speed_kmh": tel["Speed"].astype(float),
            "throttle_pct": tel["Throttle"].astype(float),
            "brake_active": tel["Brake"].astype(bool),
            "drs_status": tel["DRS"].astype(int),
            "gear": tel["nGear"].astype(int),
        }))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def write_session(con, sd, telemetry_mode="fastest", force=False):
    sid = sd.meta["session_id"]
    if session_exists(con, sid):
        if not force:
            return {"session_id": sid, "skipped": True}
        delete_session(con, sid)
    m = sd.meta
    laps_df = laps_rows(sd)
    wx_df = weather_rows(sd)
    tel_df = _telemetry_frames(sd, telemetry_mode)
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [sid, m["year"], m["round_number"], m["location"], m["session_type"], m["date_utc"],
             m.get("event_name"), m.get("total_laps"), m.get("data_source"),
             datetime.now(timezone.utc).replace(tzinfo=None)],
        )
        cols = ", ".join(laps_df.columns)
        con.register("laps_in", laps_df)
        con.execute(f"INSERT INTO laps ({cols}) SELECT {cols} FROM laps_in")
        con.unregister("laps_in")
        n_tel = 0
        if not tel_df.empty:
            con.register("tel_in", tel_df)
            con.execute(
                """
                INSERT INTO telemetry_samples (lap_id, timestamp_utc, distance_meters, speed_kmh, throttle_pct, brake_active, drs_status, gear)
                SELECT l.lap_id, t.timestamp_utc, t.distance_meters, t.speed_kmh, t.throttle_pct, t.brake_active, t.drs_status, t.gear
                FROM tel_in t JOIN laps l
                  ON l.session_id = ? AND l.driver_code = t.driver_code AND l.lap_number = t.lap_number
                """,
                [sid],
            )
            con.unregister("tel_in")
            n_tel = con.execute(
                "SELECT COUNT(*) FROM telemetry_samples t JOIN laps l USING (lap_id) WHERE l.session_id = ?", [sid]
            ).fetchall()[0][0]
        if not wx_df.empty:
            wcols = ", ".join(wx_df.columns)
            con.register("wx_in", wx_df)
            con.execute(f"INSERT INTO weather_samples ({wcols}) SELECT {wcols} FROM wx_in")
            con.unregister("wx_in")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return {"session_id": sid, "skipped": False, "laps": len(laps_df), "telemetry": int(n_tel), "weather": len(wx_df), "source": m.get("data_source")}


def list_sessions(con):
    return con.execute(
        """
        SELECT s.session_id, s.year, s.round_number, s.event_name, s.session_type, s.data_source,
               COUNT(l.lap_id) AS laps, s.loaded_at
        FROM sessions s LEFT JOIN laps l USING (session_id)
        GROUP BY ALL ORDER BY s.year, s.round_number, s.session_type
        """
    ).df()
