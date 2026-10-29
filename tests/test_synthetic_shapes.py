import numpy as np
import pandas as pd

from f1analytics.columns import LAP_COLUMNS, TELEMETRY_COLUMNS, WEATHER_COLUMNS
from f1analytics.sources import SessionKey
from f1analytics.sources.synthetic.calendar import TRACKS


def test_lap_columns_and_types(synthetic_race):
    laps = synthetic_race.laps
    assert list(laps.columns[: len(LAP_COLUMNS)]) == list(LAP_COLUMNS)
    assert pd.api.types.is_timedelta64_dtype(laps["LapTime"])
    for col in ("LapNumber", "Stint", "TyreLife", "Position"):
        assert laps[col].dtype == "float64"
    assert laps["TrackStatus"].map(type).eq(str).all()


def test_sectors_sum_to_lap_time(synthetic_race):
    laps = synthetic_race.laps
    total = laps["Sector1Time"] + laps["Sector2Time"] + laps["Sector3Time"]
    diff = (total - laps["LapTime"]).dt.total_seconds().abs()
    assert diff.max() < 0.002


def test_stint_and_tyre_life_consistent(synthetic_race):
    for _, g in synthetic_race.laps.groupby(["Driver", "Stint"]):
        life = g.sort_values("LapNumber")["TyreLife"].to_numpy()
        assert life[0] == 1
        assert np.all(np.diff(life) == 1)


def test_full_grid_and_distance(synthetic_race):
    laps = synthetic_race.laps
    assert laps["Driver"].nunique() == 20
    assert laps.groupby("Driver")["LapNumber"].max().eq(TRACKS["mexico"].laps).all()


def test_deterministic_and_distinct(source):
    a = source.load(SessionKey(2024, "Mexico", "R")).laps
    b = source.load(SessionKey(2024, "Mexico", "R")).laps
    c = source.load(SessionKey(2024, "Monza", "R")).laps
    pd.testing.assert_frame_equal(a, b)
    assert len(a) != len(c) or not a["LapTime"].equals(c["LapTime"])


def test_telemetry_shape_and_timing(synthetic_quali):
    tel = synthetic_quali.telemetry("VER")
    assert list(tel.columns[: len(TELEMETRY_COLUMNS)]) == list(TELEMETRY_COLUMNS)
    assert tel["Distance"].is_monotonic_increasing
    assert abs(tel["Distance"].max() - TRACKS["mexico"].length_m) / TRACKS["mexico"].length_m < 0.02
    lap = synthetic_quali.laps.query("Driver == 'VER' and IsAccurate")["LapTime"].min().total_seconds()
    assert abs(tel["Time"].max().total_seconds() - lap) / lap < 0.01
    assert 330 < tel["Speed"].max() < 370


def test_weather_spacing(synthetic_race):
    wx = synthetic_race.weather
    assert list(wx.columns[: len(WEATHER_COLUMNS)]) == list(WEATHER_COLUMNS)
    step = wx["Time"].diff().dropna().dt.total_seconds()
    assert step.eq(60).all()
    assert (wx["TrackTemp"] > wx["AirTemp"]).all()
