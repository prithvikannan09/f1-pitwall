import time

import numpy as np
import pandas as pd

from f1analytics import config
from f1analytics.columns import LAP_COLUMNS, TELEMETRY_COLUMNS, WEATHER_COLUMNS, conform
from f1analytics.sources.base import SessionData, make_session_id
from f1analytics.sources.codes import normalise_session

API = "https://api.openf1.org/v1"
SESSION_NAMES = {
    "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3",
    "Q": "Qualifying", "R": "Race", "S": "Sprint", "SQ": ("Sprint Qualifying", "Sprint Shootout"),
}
SC_WORDS = ("SAFETY CAR DEPLOYED",)
VSC_WORDS = ("VIRTUAL SAFETY CAR DEPLOYED",)
END_WORDS = ("SAFETY CAR IN THIS LAP", "VIRTUAL SAFETY CAR ENDING", "SAFETY CAR ENDING")


def _session(cache):
    import requests

    if not cache:
        return requests.Session()
    try:
        import requests_cache
    except ImportError:
        return requests.Session()
    folder = config.CACHE_DIR / "openf1"
    folder.mkdir(parents=True, exist_ok=True)
    return requests_cache.CachedSession(
        str(folder / "responses"),
        backend="sqlite",
        expire_after=requests_cache.NEVER_EXPIRE,
        urls_expire_after={"api.openf1.org/v1/sessions*": 86400, "api.openf1.org/v1/meetings*": 86400},
        allowable_codes=(200,),
    )


class OpenF1Source:
    name = "openf1"

    def __init__(self, timeout=30, retries=7, pause=0.4, cache=True):
        self._http = _session(cache)
        self._timeout = timeout
        self._retries = retries
        self._pause = pause

    def _get(self, endpoint, **params):
        for attempt in range(self._retries):
            r = self._http.get(f"{API}/{endpoint}", params=params, timeout=self._timeout)
            if r.status_code == 429:
                wait = r.headers.get("Retry-After")
                time.sleep(float(wait) if wait and wait.replace(".", "").isdigit() else min(2 ** attempt, 20))
                continue
            if r.status_code == 404:
                return pd.DataFrame()
            r.raise_for_status()
            if not getattr(r, "from_cache", False):
                time.sleep(self._pause)
            data = r.json()
            return pd.DataFrame(data if isinstance(data, list) else [])
        raise RuntimeError(f"OpenF1 rate limit on {endpoint}")

    def schedule(self, year):
        sessions = self._get("sessions", year=int(year))
        if sessions.empty:
            raise LookupError(f"No OpenF1 sessions for {year}")
        sessions = sessions[~sessions.get("is_cancelled", pd.Series(False, index=sessions.index)).fillna(False).astype(bool)]
        meetings = self._get("meetings", year=int(year))
        names = dict(zip(meetings["meeting_key"], meetings["meeting_name"])) if not meetings.empty else {}
        rows = []
        for i, (mk, g) in enumerate(sessions.sort_values("date_start").groupby("meeting_key", sort=False), start=1):
            g = g.sort_values("date_start")
            first = g.iloc[0]
            if "testing" in str(names.get(mk, "")).lower():
                continue
            row = {
                "RoundNumber": len(rows) + 1,
                "EventName": names.get(mk) or f"{first['country_name']} Grand Prix",
                "Location": first["location"],
                "Country": first["country_name"],
                "EventFormat": "sprint_qualifying" if g["session_name"].str.contains("Sprint").any() else "conventional",
                "EventDate": pd.Timestamp(g.iloc[-1]["date_start"]).tz_convert(None).normalize(),
                "MeetingKey": mk,
            }
            for j, (_, s) in enumerate(g.iterrows(), start=1):
                row[f"Session{j}"] = s["session_name"]
                row[f"Session{j}DateUtc"] = pd.Timestamp(s["date_start"]).tz_convert(None)
            rows.append(row)
        return pd.DataFrame(rows)

    def _resolve(self, year, gp, code):
        sched = self.schedule(year)
        if str(gp).isdigit():
            hit = sched[sched["RoundNumber"] == int(gp)]
        else:
            needle = str(gp).lower()
            hit = sched.iloc[0:0]
            for col in ("EventName", "Location", "Country"):
                hit = sched[sched[col].astype(str).str.lower().str.contains(needle, regex=False)]
                if len(hit):
                    break
        if hit.empty:
            raise LookupError(f"No event matching {gp!r} in {year}")
        event = hit.iloc[0]
        wanted = SESSION_NAMES[code]
        wanted = wanted if isinstance(wanted, tuple) else (wanted,)
        sessions = self._get("sessions", meeting_key=int(event["MeetingKey"]))
        match = sessions[sessions["session_name"].isin(wanted)]
        if match.empty:
            raise LookupError(f"{event['EventName']} has no {wanted[0]}")
        return event, match.iloc[0]

    def load(self, key, telemetry=True, weather=True):
        code = normalise_session(key.session)
        event, sess = self._resolve(int(key.year), key.gp, code)
        sk = int(sess["session_key"])
        start = pd.Timestamp(sess["date_start"]).tz_convert(None)
        drivers = self._get("drivers", session_key=sk)
        laps_raw = self._get("laps", session_key=sk)
        if laps_raw.empty:
            raise LookupError("OpenF1 returned no laps")
        stints = self._get("stints", session_key=sk)
        pits = self._get("pit", session_key=sk)
        control = self._get("race_control", session_key=sk)
        laps = build_laps(laps_raw, drivers, stints, pits, control, start)
        wx = build_weather(self._get("weather", session_key=sk), start) if weather else conform(pd.DataFrame(), WEATHER_COLUMNS)
        meta = {
            "session_id": make_session_id(key.year, event["RoundNumber"], code),
            "year": int(key.year),
            "round_number": int(event["RoundNumber"]),
            "event_name": str(event["EventName"]),
            "location": str(event["Location"]),
            "session_type": code,
            "date_utc": start.to_pydatetime(),
            "total_laps": int(laps["LapNumber"].max() or 0),
            "data_source": self.name,
        }
        numbers = dict(zip(laps["Driver"], laps["DriverNumber"]))

        def tel(driver, lap_number):
            rows = laps[laps["Driver"] == driver]
            if lap_number == -1:
                valid = rows[rows["IsAccurate"] & rows["LapTime"].notna()]
                valid = valid if len(valid) else rows[rows["LapTime"].notna()]
                if valid.empty:
                    raise LookupError(f"No timed lap for {driver}")
                row = valid.loc[valid["LapTime"].idxmin()]
            else:
                hit = rows[rows["LapNumber"] == lap_number]
                if hit.empty:
                    raise LookupError(f"No lap {lap_number} for {driver}")
                row = hit.iloc[0]
            t0 = start + row["LapStartTime"]
            t1 = t0 + row["LapTime"]
            raw = self._get("car_data", **{"session_key": sk, "driver_number": int(numbers[driver]), "date>": t0.isoformat(), "date<": t1.isoformat()})
            if raw.empty:
                raise LookupError(f"No car data for {driver} lap {int(row['LapNumber'])}")
            return build_telemetry(raw, t0, start)

        return SessionData(meta, laps, wx, tel if telemetry else None)


def _ts(series):
    return pd.to_datetime(series, utc=True, format="ISO8601").dt.tz_convert(None)


def _status_windows(control):
    if control is None or control.empty or "message" not in control:
        return []
    flag = control["flag"].fillna("").str.upper() if "flag" in control else pd.Series("", index=control.index)
    msgs = control.assign(t=_ts(control["date"]), m=control["message"].fillna("").str.upper(), f=flag).sort_values("t")
    windows, open_code, opened = [], None, None
    for _, r in msgs.iterrows():
        is_green = r["f"] == "GREEN" or "GREEN LIGHT" in r["m"] or "TRACK CLEAR" in r["m"]
        if any(w in r["m"] for w in VSC_WORDS):
            open_code, opened = "6", r["t"]
        elif any(w in r["m"] for w in SC_WORDS):
            open_code, opened = "4", r["t"]
        elif r["f"] == "RED" or r["m"].startswith("RED FLAG"):
            if open_code:
                windows.append((opened, r["t"], open_code))
            open_code, opened = "5", r["t"]
        elif open_code and (any(w in r["m"] for w in END_WORDS) or is_green):
            windows.append((opened, r["t"], open_code))
            open_code = None
    if open_code:
        windows.append((opened, opened + pd.Timedelta(minutes=10), open_code))
    return windows


def build_laps(laps_raw, drivers, stints, pits, control, start):
    df = laps_raw.copy()
    df["lap_start"] = _ts(df["date_start"])
    df = df.sort_values(["driver_number", "lap_number"])
    df["lap_start"] = df.groupby("driver_number")["lap_start"].transform(lambda s: s.fillna(s.shift(1)))
    info = drivers.drop_duplicates("driver_number").set_index("driver_number") if not drivers.empty else pd.DataFrame()
    code = df["driver_number"].map(info["name_acronym"]) if "name_acronym" in info else df["driver_number"].astype(str)
    team = df["driver_number"].map(info["team_name"]) if "team_name" in info else None
    dur = pd.to_numeric(df["lap_duration"], errors="coerce")
    end = df["lap_start"] + pd.to_timedelta(dur, unit="s")
    out = pd.DataFrame({
        "Driver": code.fillna(df["driver_number"].astype(str)).values,
        "DriverNumber": df["driver_number"].astype(str).values,
        "Team": team.values if team is not None else None,
        "LapNumber": df["lap_number"].astype(float).values,
        "LapTime": pd.to_timedelta(dur, unit="s").values,
        "Sector1Time": pd.to_timedelta(pd.to_numeric(df["duration_sector_1"], errors="coerce"), unit="s").values,
        "Sector2Time": pd.to_timedelta(pd.to_numeric(df["duration_sector_2"], errors="coerce"), unit="s").values,
        "Sector3Time": pd.to_timedelta(pd.to_numeric(df["duration_sector_3"], errors="coerce"), unit="s").values,
        "SpeedST": pd.to_numeric(df.get("st_speed"), errors="coerce").values,
        "LapStartTime": (df["lap_start"] - start).values,
        "Time": (end - start).values,
        "Deleted": False,
    })
    pit_out = df["is_pit_out_lap"].fillna(False).astype(bool).to_numpy()
    out["PitOutTime"] = pd.Series((df["lap_start"] - start + pd.Timedelta(seconds=5)).to_numpy()).where(pit_out)
    out["PitInTime"] = pd.Series(pd.NaT, index=out.index, dtype="timedelta64[ns]")
    if pits is not None and not pits.empty and "lap_number" in pits:
        pit_keys = set(zip(pits["driver_number"].astype(str), pits["lap_number"].astype(float)))
        mask = [(n, l) in pit_keys for n, l in zip(out["DriverNumber"], out["LapNumber"])]
        out.loc[mask, "PitInTime"] = out.loc[mask, "Time"] - pd.Timedelta(seconds=3)
    out["Stint"], out["Compound"], out["TyreLife"] = np.nan, None, np.nan
    if stints is not None and not stints.empty:
        for _, s in stints.iterrows():
            m = (out["DriverNumber"] == str(s["driver_number"])) & out["LapNumber"].between(s["lap_start"], s["lap_end"])
            age0 = s.get("tyre_age_at_start")
            age0 = 0 if pd.isna(age0) else age0
            out.loc[m, "Stint"] = float(s["stint_number"])
            out.loc[m, "Compound"] = str(s["compound"]).upper() if pd.notna(s["compound"]) else "UNKNOWN"
            out.loc[m, "TyreLife"] = out.loc[m, "LapNumber"] - s["lap_start"] + 1 + age0
    status = pd.Series("1", index=out.index, dtype=object)
    abs_start = out["LapStartTime"] + start
    abs_end = out["Time"] + start
    for t0, t1, c in _status_windows(control):
        overlap = (abs_start < t1) & (abs_end > t0)
        current = status[overlap]
        status[overlap] = np.where(current == "1", c, current + c)
    out["TrackStatus"] = status
    out["IsAccurate"] = (
        out["LapTime"].notna() & (out["LapNumber"] > 1) & out["PitOutTime"].isna() & out["PitInTime"].isna() & (status == "1")
    )
    out["Position"] = out.groupby("LapNumber")["Time"].rank(method="first")
    return conform(out.sort_values(["Driver", "LapNumber"]), LAP_COLUMNS)


def build_weather(raw, start):
    if raw.empty:
        return conform(pd.DataFrame(), WEATHER_COLUMNS)
    t = _ts(raw["date"])
    df = pd.DataFrame({
        "Time": (t - start).values,
        "AirTemp": raw["air_temperature"], "Humidity": raw["humidity"], "Pressure": raw["pressure"],
        "Rainfall": raw["rainfall"].fillna(0).astype(bool), "TrackTemp": raw["track_temperature"],
        "WindDirection": raw["wind_direction"], "WindSpeed": raw["wind_speed"],
    })
    df = df[df["Time"] >= pd.Timedelta(0)].sort_values("Time")
    return conform(df, WEATHER_COLUMNS)


def build_telemetry(raw, lap_start, session_start):
    df = raw.copy()
    df["Date"] = _ts(df["date"])
    df = df.sort_values("Date").reset_index(drop=True)
    rel = (df["Date"] - lap_start).dt.total_seconds().to_numpy()
    speed = pd.to_numeric(df["speed"], errors="coerce").fillna(0).to_numpy(float)
    dt = np.diff(rel, prepend=rel[0])
    dist = np.cumsum(speed / 3.6 * dt)
    out = pd.DataFrame({
        "Date": df["Date"],
        "SessionTime": df["Date"] - session_start,
        "Time": pd.to_timedelta(rel, unit="s"),
        "RPM": df.get("rpm"),
        "Speed": speed,
        "nGear": df.get("n_gear"),
        "Throttle": df.get("throttle"),
        "Brake": pd.to_numeric(df.get("brake"), errors="coerce").fillna(0) > 0,
        "DRS": df.get("drs"),
        "Distance": dist,
    })
    return conform(out, TELEMETRY_COLUMNS)
