import pandas as pd

from f1analytics import config
from f1analytics.columns import LAP_COLUMNS, TELEMETRY_COLUMNS, WEATHER_COLUMNS, conform
from f1analytics.sources.base import SessionData, make_session_id
from f1analytics.sources.codes import normalise_session


class FastF1Source:
    name = "fastf1"

    def __init__(self, cache_dir=None, offline=False):
        import fastf1

        self._f1 = fastf1
        cache = config.CACHE_DIR if cache_dir is None else cache_dir
        cache.mkdir(parents=True, exist_ok=True)
        fastf1.set_log_level("ERROR")
        if hasattr(fastf1.Cache, "configure"):
            fastf1.Cache.configure(cache_dir=str(cache))
        else:
            fastf1.Cache.enable_cache(str(cache))
        fastf1.Cache.offline_mode(bool(offline))

    def schedule(self, year):
        return pd.DataFrame(self._f1.get_event_schedule(int(year), include_testing=False))

    def load(self, key, telemetry=True, weather=True):
        code = normalise_session(key.session)
        gp = int(key.gp) if str(key.gp).isdigit() else key.gp
        session = self._f1.get_session(int(key.year), gp, code)
        session.load(laps=True, telemetry=telemetry, weather=weather, messages=False)
        laps = conform(pd.DataFrame(session.laps), LAP_COLUMNS)
        wx = conform(pd.DataFrame(session.weather_data), WEATHER_COLUMNS) if weather and session.weather_data is not None else conform(pd.DataFrame(), WEATHER_COLUMNS)
        event = session.event
        try:
            date_utc = event.get_session_date(session.name, utc=True)
        except (ValueError, KeyError, AttributeError):
            date_utc = pd.Timestamp(event["EventDate"])
        try:
            total = session.total_laps
        except Exception:
            total = None
        meta = {
            "session_id": make_session_id(key.year, event["RoundNumber"], code),
            "year": int(key.year),
            "round_number": int(event["RoundNumber"]),
            "event_name": str(event["EventName"]),
            "location": str(event["Location"]),
            "session_type": code,
            "date_utc": pd.Timestamp(date_utc).tz_localize(None).to_pydatetime() if pd.Timestamp(date_utc).tzinfo else pd.Timestamp(date_utc).to_pydatetime(),
            "total_laps": int(total) if total else int(laps["LapNumber"].max() or 0),
            "data_source": self.name,
        }
        tel = self._telemetry_fn(session) if telemetry else None
        return SessionData(meta, laps, wx, tel)

    @staticmethod
    def _telemetry_fn(session):
        def tel(driver, lap_number):
            driver_laps = session.laps.pick_drivers(driver)
            if lap_number == -1:
                lap = driver_laps.pick_fastest()
            else:
                picked = driver_laps.pick_laps(int(lap_number))
                lap = picked.iloc[0] if len(picked) else None
            if lap is None or (hasattr(lap, "empty") and lap.empty):
                raise LookupError(f"No lap {lap_number} for {driver}")
            return conform(pd.DataFrame(lap.get_car_data().add_distance()), TELEMETRY_COLUMNS)

        return tel
