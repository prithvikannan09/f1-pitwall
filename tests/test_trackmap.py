import math
from pathlib import Path

from streamlit.testing.v1 import AppTest

from f1analytics.pitwall.tracks import circuit_key_for

PAGE = str(Path(__file__).resolve().parent.parent / "pages" / "1_Pit_Wall.py")


def test_circuit_keys():
    assert circuit_key_for("Austin") == 9
    assert circuit_key_for(None, "Mexico City Grand Prix") == 65
    assert circuit_key_for("Las Vegas") == 152
    assert circuit_key_for("Nowhere") is None


def test_track_layout_used_when_available(monkeypatch):
    import f1analytics.ui.pitwall_page as pw

    n = 400
    fake = {"x": [1000 * math.cos(2 * math.pi * i / n) for i in range(n)], "y": [600 * math.sin(2 * math.pi * i / n) for i in range(n)],
            "rotation": 0.0, "corners": [(1, 1000.0, 0.0), (2, 0.0, 600.0)]}
    calls = []

    def fake_outline(key, year):
        calls.append((key, year))
        return fake

    monkeypatch.setattr(pw, "circuit_outline", fake_outline)
    at = AppTest.from_file(PAGE, default_timeout=120)
    at.run()
    at.sidebar.radio[0].set_value("Replay").run()
    at.slider(key="pw_lap").set_value(20).run()
    assert not at.exception and not at.error
    assert (9, 2026) in calls
    assert any("Track (from gaps)" in h.value for h in at.subheader)
    assert any("start line" in c.value for c in at.caption)
