from pathlib import Path

from streamlit.testing.v1 import AppTest

from f1analytics.pitwall.conditions import air_density, altitude_from_pressure, analyse

PAGE = str(Path(__file__).resolve().parent.parent / "pages" / "1_Pit_Wall.py")


def test_physics():
    assert abs(air_density(1013.25, 15, 0) - 1.225) < 0.005
    assert 2000 < altitude_from_pressure(780.8) < 2400
    assert altitude_from_pressure(1013.25) < 5


def test_mexico_thin_air():
    c = analyse({"AirTemp": 25.2, "TrackTemp": 38.7, "Humidity": 26, "Rainfall": 0, "WindSpeed": 2.2, "Pressure": 780.8})
    assert 22 < c["thinner_pct"] < 29
    names = [n for n, _ in c["effects"]]
    assert "Less grip in corners" in names and "Hard to keep cool" in names and "Faster on the straights" in names


def test_austin_normal_air():
    c = analyse({"AirTemp": 27.3, "TrackTemp": 36, "Humidity": 39, "Rainfall": 0, "WindSpeed": 2.9, "Pressure": 1004.1})
    assert c["thinner_pct"] < 6
    assert "Less grip in corners" not in [n for n, _ in c["effects"]]


def test_hot_track_and_rain():
    c = analyse({"AirTemp": 30, "TrackTemp": 52, "Rainfall": 1})
    names = [n for n, _ in c["effects"]]
    assert "Hot track" in names and "Rain" in names and c["density"] is None


def test_conditions_on_page():
    at = AppTest.from_file(PAGE, default_timeout=120)
    at.run()
    at.radio(key="pw_mode").set_value("Past races").run()
    at.selectbox(key="pw_year").set_value("Saved replays (offline)").run()
    at.selectbox(key="pw_saved").set_value("2025 Mexico · Practice 2 (bundled)").run()
    assert not at.exception and not at.error
    assert any(h.value.startswith("Conditions") for h in at.subheader)
    assert any("Hot and dry" in h.value or "Dry" in h.value for h in at.subheader)
    text = " ".join(m.value for m in at.markdown)
    assert "thinner air" in text and "Less grip in corners" in text



def test_weather_backdrop_kinds():
    from f1analytics.pitwall.conditions import theme_css, weather_kind

    assert weather_kind(analyse({"AirTemp": 20, "TrackTemp": 30, "Rainfall": 1}))[0] == "wet"
    assert weather_kind(analyse({"AirTemp": 33, "TrackTemp": 50}))[0] == "hot"
    assert weather_kind(analyse({"AirTemp": 12, "TrackTemp": 20}))[0] == "cool"
    assert weather_kind(analyse({"AirTemp": 22, "TrackTemp": 35}))[0] == "mild"
    assert weather_kind(analyse({}))[0] is None and theme_css(None) == ""
    css = theme_css("wet")
    assert "pw-rain" in css and "prefers-reduced-motion" in css
