import pandas as pd

from f1analytics.pitwall import forecast


def hours(temp, prob, mm, code=3):
    t = pd.date_range("2026-11-06T13:00", periods=8, freq="h", tz="UTC")
    return pd.DataFrame({"time": t, "temperature_2m": temp, "precipitation_probability": prob, "precipitation": mm,
                         "weather_code": code, "wind_speed_10m": 3.0, "relative_humidity_2m": 70.0, "cloud_cover": 90.0})


def test_interlagos_coords():
    assert forecast.coords("Interlagos", "São Paulo") == (-23.7036, -46.6997)
    assert forecast.coords("Yas Marina Circuit", "Yas Marina")
    assert forecast.coords("Nowhere", "") is None


def test_dry_fp1():
    f = forecast.summarise(hours(21.0, 14.0, 0.0), "2026-11-06T15:30Z", "2026-11-06T16:30Z")
    assert f["kind"] == "dry"
    assert forecast.headline(f).startswith("Dry ·")


def test_wet_by_probability_or_amount():
    assert forecast.summarise(hours(16.0, 95.0, 0.6, 53), "2026-11-06T15:00Z", "2026-11-06T17:00Z")["kind"] == "rain"
    assert forecast.summarise(hours(20.0, 20.0, 0.3), "2026-11-06T14:00Z", "2026-11-06T17:00Z")["kind"] == "rain"


def test_hot_and_shower_warning():
    f = forecast.summarise(hours(31.0, 40.0, 0.0), "2026-11-06T15:00Z", "2026-11-06T16:00Z")
    assert f["kind"] == "hot"
    assert "chance of a shower" in forecast.headline(f)


def test_outside_window_and_missing():
    assert forecast.summarise(hours(20.0, 0.0, 0.0), "2026-12-01T10:00Z", "2026-12-01T11:00Z") is None
    assert forecast.headline(None) == "Forecast not out yet"


def test_scene_snap_gives_local_daytime():
    from f1analytics.ui import themes
    wf = {"meeting": "São Paulo", "circuit": "Interlagos",
          "sessions": [{"session": "Practice 1", "start": "2026-11-06T15:30:00+00:00", "gmt_offset": "-03:00:00", "forecast": None}]}
    assert themes.time_of_day(forecast.scene_snap(wf)) == "day"
