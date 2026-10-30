from pathlib import Path

from streamlit.testing.v1 import AppTest

PAGE = str(Path(__file__).resolve().parent.parent / "pages" / "1_Pit_Wall.py")


def _replay(params=None):
    at = AppTest.from_file(PAGE, default_timeout=120)
    for k, v in (params or {}).items():
        at.query_params[k] = v
    at.run()
    at.sidebar.radio[0].set_value("Replay").run()
    at.slider(key="pw_lap").set_value(14).run()
    assert not at.exception and not at.error
    return at


def test_default_follows_hamilton_and_title():
    at = _replay()
    assert at.title[0].value == "F1 Pit Wall"
    assert at.selectbox(key="pw_team").value == "Ferrari"
    assert at.selectbox(key="pw_driver").value == "HAM"
    assert "⭐ HAM" in " ".join(m.value for m in at.markdown)


def test_link_opens_on_any_driver():
    at = _replay({"driver": "VER"})
    assert at.selectbox(key="pw_team").value == "Red Bull Racing"
    assert at.selectbox(key="pw_driver").value == "VER"
    text = " ".join(m.value for m in at.markdown)
    assert "Following ⭐ VER" in text and "VER" in text
    assert at.query_params["driver"] == "VER"


def test_team_link_and_switching_team():
    at = _replay({"team": "mclaren"})
    assert at.selectbox(key="pw_team").value == "McLaren"
    assert at.selectbox(key="pw_driver").value in ("NOR", "PIA")
    at.selectbox(key="pw_team").set_value("Mercedes").run()
    assert not at.exception and not at.error
    assert at.selectbox(key="pw_driver").value in ("RUS", "ANT")
    at.selectbox(key="pw_driver").set_value("RUS").run()
    assert at.query_params["driver"] == "RUS" and at.query_params["team"] == "Mercedes"
