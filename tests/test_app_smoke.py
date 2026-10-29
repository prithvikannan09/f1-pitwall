from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_renders_every_tab(tmp_path, monkeypatch):
    monkeypatch.setenv("F1_DB_PATH", str(tmp_path / "f1.duckdb"))
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    assert len(at.tabs) == 8
    labels = {m.label for m in at.metric}
    assert {"Top speed", "Undercut works", "Track temp"} <= labels


def test_pit_wall_page_live_and_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("F1_LIVE_DIR", str(tmp_path))
    page = str(Path(__file__).resolve().parent.parent / "pages" / "1_Pit_Wall.py")
    at = AppTest.from_file(page, default_timeout=120)
    at.run()
    assert not at.exception
    at.sidebar.radio[0].set_value("Replay").run()
    at.slider(key="pw_lap").set_value(14).run()
    assert not at.exception and not at.error
    assert any("BOX THIS LAP" in m.value for m in at.markdown)


def test_pit_wall_practice_replay():
    page = str(Path(__file__).resolve().parent.parent / "pages" / "1_Pit_Wall.py")
    at = AppTest.from_file(page, default_timeout=120)
    at.run()
    at.sidebar.radio[0].set_value("Replay").run()
    at.sidebar.radio[1].set_value("2025 Mexico · Practice 2 (bundled)").run()
    assert not at.exception and not at.error
    text = " ".join(m.value for m in at.markdown)
    assert "HAM" in text and "Long runs" in text and "Wing level" in text
