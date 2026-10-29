import zlib

import numpy as np
import pandas as pd

from f1analytics.sources.base import SessionData, make_session_id
from f1analytics.sources.codes import normalise_session
from f1analytics.sources.synthetic.calendar import DRIVERS, resolve_event, schedule, track_for
from f1analytics.sources.synthetic.laps import generate_laps
from f1analytics.sources.synthetic.telemetry import generate_telemetry
from f1analytics.sources.synthetic.weather import generate_weather

SESSION_NAMES = {
    "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3",
    "Q": "Qualifying", "R": "Race", "SQ": "Sprint Qualifying", "S": "Sprint",
}


def _seed(*parts):
    return zlib.crc32("|".join(str(p) for p in parts).encode())


class SyntheticSource:
    name = "synthetic"

    def schedule(self, year):
        return schedule(year)

    def load(self, key, telemetry=True, weather=True):
        code = normalise_session(key.session)
        event = resolve_event(key.year, key.gp)
        track = track_for(event)
        seed = _seed(key.year, event["EventName"], code)
        rng = np.random.default_rng(seed)
        laps = generate_laps(track, code, rng)
        name = SESSION_NAMES[code]
        date_col = next((c for c in event.index if c.startswith("Session") and event[c] == name), None)
        date_utc = event.get(f"{date_col}DateUtc") if date_col else event["EventDate"]
        if pd.isna(date_utc):
            date_utc = event["EventDate"]
        end = laps["Time"].max().total_seconds() if len(laps) else 3600
        wx = generate_weather(track, end + 600, np.random.default_rng(seed + 1)) if weather else generate_weather(track, 0, rng).iloc[0:0]
        pace = {d[0]: d[3] for d in DRIVERS}
        drs_open = code not in {"R", "S"}

        def tel(driver, lap_number):
            rows = laps[laps["Driver"] == driver]
            if lap_number == -1:
                valid = rows[rows["IsAccurate"] & rows["LapTime"].notna()]
                if valid.empty:
                    raise LookupError(f"No timed lap for {driver}")
                row = valid.loc[valid["LapTime"].idxmin()]
            else:
                hit = rows[rows["LapNumber"] == lap_number]
                if hit.empty:
                    raise LookupError(f"No lap {lap_number} for {driver}")
                row = hit.iloc[0]
            factor = 1.0 - pace.get(driver, 0.5) / 300
            return generate_telemetry(
                track, row["LapTime"].total_seconds(), factor, drs_open,
                np.random.default_rng(_seed(seed, driver)),
                start_date=date_utc, session_time=row["LapStartTime"],
            )

        meta = {
            "session_id": make_session_id(key.year, event["RoundNumber"], code),
            "year": int(key.year),
            "round_number": int(event["RoundNumber"]),
            "event_name": event["EventName"],
            "location": event["Location"],
            "session_type": code,
            "date_utc": pd.Timestamp(date_utc).to_pydatetime(),
            "total_laps": int(laps["LapNumber"].max()) if len(laps) else 0,
            "data_source": self.name,
        }
        return SessionData(meta, laps, wx, tel if telemetry else None)
