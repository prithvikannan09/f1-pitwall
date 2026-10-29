from unittest import mock

import pandas as pd

from f1analytics.columns import LAP_COLUMNS
from f1analytics.sources import SessionKey, load_with_fallback
from f1analytics.sources.openf1_source import _status_windows, build_laps, build_telemetry, build_weather

START = pd.Timestamp("2024-10-27 20:00:00")


def _iso(seconds):
    return (START + pd.Timedelta(seconds=seconds)).tz_localize("UTC").isoformat()


def _laps():
    rows = []
    for num in (1, 55):
        t = 0.0
        for lap in range(1, 7):
            dur = 80.0 + lap * 0.1 + (0.5 if num == 55 else 0)
            rows.append({
                "driver_number": num, "lap_number": lap, "date_start": _iso(t), "lap_duration": dur,
                "duration_sector_1": 25.0, "duration_sector_2": 30.0, "duration_sector_3": dur - 55.0,
                "st_speed": 340 + lap, "is_pit_out_lap": lap == 4,
            })
            t += dur
    return pd.DataFrame(rows)


DRIVERS = pd.DataFrame({"driver_number": [1, 55], "name_acronym": ["VER", "SAI"], "team_name": ["Red Bull Racing", "Ferrari"]})
STINTS = pd.DataFrame({
    "driver_number": [1, 1, 55, 55], "stint_number": [1, 2, 1, 2], "lap_start": [1, 4, 1, 4],
    "lap_end": [3, 6, 3, 6], "compound": ["MEDIUM", "HARD", "SOFT", "HARD"], "tyre_age_at_start": [0, 0, 2, 0],
})
PITS = pd.DataFrame({"driver_number": [1, 55], "lap_number": [3, 3]})
CONTROL = pd.DataFrame({
    "date": [_iso(5), _iso(170), _iso(470)],
    "message": ["SAFETY CAR DEPLOYED", "SAFETY CAR IN THIS LAP", "CHEQUERED FLAG"],
    "flag": [None, None, "CHEQUERED"],
})


def test_build_laps_shape_and_tyres():
    laps = build_laps(_laps(), DRIVERS, STINTS, PITS, CONTROL, START)
    assert set(LAP_COLUMNS) <= set(laps.columns)
    sai = laps[laps["Driver"] == "SAI"].set_index("LapNumber")
    assert sai.loc[1, "Compound"] == "SOFT" and sai.loc[1, "TyreLife"] == 3
    assert sai.loc[4, "Compound"] == "HARD" and sai.loc[4, "TyreLife"] == 1
    assert pd.notna(sai.loc[3, "PitInTime"]) and pd.notna(sai.loc[4, "PitOutTime"])
    assert pd.api.types.is_timedelta64_dtype(laps["PitOutTime"]) and pd.api.types.is_timedelta64_dtype(laps["PitInTime"])
    lap2 = laps[laps["LapNumber"] == 2].set_index("Driver")["Position"]
    assert lap2["VER"] == 1 and lap2["SAI"] == 2


def test_safety_car_marked_and_chequered_is_not_red():
    laps = build_laps(_laps(), DRIVERS, STINTS, PITS, CONTROL, START)
    by_lap = laps[laps["Driver"] == "VER"].set_index("LapNumber")["TrackStatus"]
    assert by_lap.loc[1] == "4" and by_lap.loc[2] == "4"
    assert by_lap.loc[6] == "1"
    assert not laps["TrackStatus"].str.contains("5").any()


def test_red_flag_window():
    control = pd.DataFrame({"date": [_iso(100), _iso(200)], "message": ["RED FLAG", "GREEN LIGHT - PIT EXIT OPEN"], "flag": ["RED", "GREEN"]})
    windows = _status_windows(control)
    assert len(windows) == 1 and windows[0][2] == "5"


def test_build_weather_and_telemetry():
    wx = build_weather(pd.DataFrame({
        "date": [_iso(-60), _iso(0), _iso(60)], "air_temperature": [20, 21, 22], "track_temperature": [40, 41, 42],
        "humidity": [50, 50, 50], "pressure": [780, 780, 780], "rainfall": [0, 0, 1], "wind_direction": [10, 10, 10], "wind_speed": [1, 1, 1],
    }), START)
    assert len(wx) == 2 and wx["Rainfall"].tolist() == [False, True]
    raw = pd.DataFrame({"date": [_iso(10 + i) for i in range(5)], "speed": [360.0] * 5, "throttle": [100] * 5,
                        "brake": [0, 0, 100, 0, 0], "n_gear": [8] * 5, "rpm": [11000] * 5, "drs": [12] * 5})
    tel = build_telemetry(raw, START + pd.Timedelta(seconds=10), START)
    assert abs(tel["Distance"].iloc[-1] - 400.0) < 1e-6
    assert tel["Brake"].tolist() == [False, False, True, False, False]


def test_auto_prefers_openf1_when_reachable():
    fake = mock.MagicMock()
    fake.load.return_value.laps = pd.DataFrame({"x": [1]})
    with mock.patch("f1analytics.sources.online", return_value=True), \
         mock.patch("f1analytics.sources.has_f1_login", return_value=False), \
         mock.patch("f1analytics.sources._openf1", return_value=fake):
        assert load_with_fallback(SessionKey(2024, "Mexico", "R"), mode="auto") is fake.load.return_value
