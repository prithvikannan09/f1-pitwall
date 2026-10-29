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
