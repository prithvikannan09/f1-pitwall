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


def test_buildup_for_interlagos():
    from f1analytics.pitwall import preview as pv
    b = pv.build("São Paulo")
    if b is None:
        return
    assert not b["ranked"].empty
    assert b["lap_s"] == 72.0
    easy, hard = pv.tyre_board(b["table"])
    assert easy and hard and easy[0][1] <= hard[0][1]


def test_buildup_panel_renders():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string("""
from f1analytics.ui.buildup_panel import buildup_section
buildup_section("São Paulo", "HAM", "rain")
""").run(timeout=60)
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "HAM this weekend" in text and "Rain is forecast" in text


def test_weekend_falls_back_to_saved_schedule(monkeypatch):
    def locked(*a, **k):
        return {"detail": "Live F1 session in progress"}
    monkeypatch.setattr(forecast, "_get", locked)
    wk = forecast.weekend("2026-11-06T16:40:00Z")
    assert list(wk["session_name"])[:2] == ["Practice 2", "Practice 3"]
    assert wk.iloc[0]["circuit_short_name"] == "Interlagos"


def test_countdown_counts_down_from_server_time():
    from f1analytics.ui.pitwall_page import countdown_markup
    h = countdown_markup("Practice 2", "2026-11-06T19:00:00+00:00", "Fri 16:00 local", "Sat 12:30 AM IST", "#FFCC00",
                         now="2026-11-06T17:30:00+00:00")
    assert "--cd-from:5400" in h and "cd-run 5400s" in h
    assert "FP2 starts in" in h and "Sat 12:30 AM IST" in h and "#FFCC00" in h
    assert "<iframe" not in h and "<script" not in h
    done = countdown_markup("Practice 2", "2026-11-06T19:00:00+00:00", "x", "y", now="2026-11-06T19:05:00+00:00")
    assert "--cd-from:0" in done and "is under way" in done


def test_weekend_notes_for_sao_paulo():
    from f1analytics.ui.buildup_panel import weekend_notes
    n = weekend_notes("São Paulo")
    assert n and {p["code"] for p in n["penalties"]} >= {"HAM", "LEC", "VER"}
    assert all(u.startswith("https://") for _, u in n["sources"])
    assert weekend_notes("Las Vegas") is None


def test_focus_alert_mentions_smoke_and_penalty():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string("""
from f1analytics.ui.buildup_panel import focus_alert, top_notes
focus_alert("São Paulo Grand Prix", "HAM")
top_notes("São Paulo", "HAM")
""").run(timeout=60)
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "smoke in the cockpit" in text.lower() and "10 places" in text and "Back of grid" in text
    assert any("Why do engine changes" in e.label for e in at.expander)
