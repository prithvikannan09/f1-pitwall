from dataclasses import dataclass, field
from typing import Callable, Protocol

import pandas as pd


@dataclass(frozen=True)
class SessionKey:
    year: int
    gp: object
    session: str


@dataclass
class SessionData:
    meta: dict
    laps: pd.DataFrame
    weather: pd.DataFrame
    _telemetry_fn: Callable = field(repr=False, default=None)

    def telemetry(self, driver, lap_number=-1):
        if self._telemetry_fn is None:
            raise LookupError("telemetry not loaded")
        return self._telemetry_fn(driver, int(lap_number))

    @property
    def drivers(self):
        return sorted(self.laps["Driver"].dropna().unique().tolist())

    @property
    def is_race(self):
        return self.meta.get("session_type") in {"R", "S"}


def make_session_id(year, round_number, code):
    return f"{int(year)}_{int(round_number):02d}_{code}"


class DataSource(Protocol):
    name: str

    def schedule(self, year): ...

    def load(self, key, telemetry=True, weather=True): ...
