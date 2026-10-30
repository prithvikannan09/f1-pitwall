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
    at.radio(key="pw_mode").set_value("Past races").run()
    at.slider(key="pw_lap").set_value(20).run()
    assert not at.exception and not at.error
    assert (9, 2026) in calls
    assert any("Track (from gaps)" in h.value for h in at.subheader)
    assert any("start line" in c.value for c in at.caption)


def test_replay_shows_gps_from_openf1(monkeypatch):
    import f1analytics.ui.pitwall_page as pw
    from f1analytics.live.replay import RaceReplay, load_fixture

    rep = RaceReplay(load_fixture(Path(__file__).resolve().parent.parent / "f1analytics" / "replays" / "usgp2026"))
    snap = rep.snapshot(20)
    assert snap["session_key"] == 11396 and snap["circuit_key"] == 9 and snap["now_utc"].startswith("2026-10-25")
    seen = {}

    def fake_positions(sk, iso):
        seen["args"] = (sk, iso)
        return {d["number"]: {"x": 100.0 * i, "y": 50.0 * i} for i, d in enumerate(snap["drivers"])}

    monkeypatch.setattr(pw, "replay_positions", fake_positions)
    out = pw.add_replay_gps(snap)
    assert out["positions_source"] == "replay" and len(out["positions"]) == len(snap["drivers"])
    assert seen["args"] == (11396, snap["now_utc"])

    monkeypatch.setattr(pw, "circuit_outline", lambda k, y: None)
    at = AppTest.from_file(PAGE, default_timeout=120)
    at.run()
    at.radio(key="pw_mode").set_value("Past races").run()
    at.slider(key="pw_lap").set_value(20).run()
    assert not at.exception and not at.error
    assert "Track map (GPS)" in [h.value for h in at.subheader]


def test_any_session_picker(monkeypatch):
    import f1analytics.ui.pitwall_page as pw
    from f1analytics.live.replay import load_fixture

    fake = [{"round": 1, "meeting": "Australian Grand Prix", "location": "Melbourne", "session": "Practice 1", "type": "Practice", "session_key": 1, "date": "2026-03-06"},
            {"round": 20, "meeting": "United States Grand Prix", "location": "Austin", "session": "Qualifying", "type": "Qualifying", "session_key": 2, "date": "2026-10-24"},
            {"round": 20, "meeting": "United States Grand Prix", "location": "Austin", "session": "Race", "type": "Race", "session_key": 11396, "date": "2026-10-25"}]
    monkeypatch.setattr(pw, "season_list", lambda y: fake)
    loaded = []

    def fake_load(sk):
        loaded.append(sk)
        return load_fixture(Path(__file__).resolve().parent.parent / "f1analytics" / "replays" / "usgp2026")

    import f1analytics.live.replay as rp

    monkeypatch.setattr(rp, "load_openf1_session", fake_load)
    pw.get_replay.clear()
    at = AppTest.from_file(PAGE, default_timeout=120)
    at.run()
    at.radio(key="pw_mode").set_value("Past races").run()
    assert not at.exception and not at.error, [e.value for e in at.exception]
    assert at.selectbox(key="pw_round_2026").value == 20
    assert at.selectbox(key="pw_sess_2026_20").value == 11396
    assert loaded == [11396]
    assert any("BOX" in m.value or "STAY OUT" in m.value for m in at.markdown)


def test_smooth_lap_animation(monkeypatch):
    import numpy as np

    import f1analytics.ui.pitwall_page as pw
    from f1analytics.ui.race_anim import project_traces

    th = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    outline = {"x": list(1000 * np.cos(th)), "y": list(600 * np.sin(th)), "rotation": 0.0, "corners": []}
    calls = {}

    def fake_trace(sk, t0, t1):
        calls["win"] = (sk, t0, t1)
        t = np.arange(0, 100, 0.27)
        out = {}
        for i, n in enumerate(["44", "16", "1", "63"]):
            a = 2 * np.pi * (t / 95 - i * 0.02)
            out[n] = (t.tolist(), (1000 * np.cos(a)).tolist(), (600 * np.sin(a)).tolist())
        return out

    monkeypatch.setattr(pw, "circuit_outline", lambda k, y: outline)
    monkeypatch.setattr(pw, "lap_trace", fake_trace)
    at = AppTest.from_file(PAGE, default_timeout=120)
    at.run()
    at.radio(key="pw_mode").set_value("Past races").run()
    at.slider(key="pw_lap").set_value(20).run()
    assert not at.exception and not at.error
    assert "Track map (GPS)" in [h.value for h in at.subheader]
    assert any("snapped to the track" in c.value for c in at.caption)
    sk, t0, t1 = calls["win"]
    assert sk == 11396 and t0 < t1 and t0.startswith("2026-10-25")
    _, _, total, along = project_traces(outline["x"], outline["y"], fake_trace(0, 0, 0))
    for t, s in along.values():
        assert all(b >= a for a, b in zip(s, s[1:]))
