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
    at.sidebar.radio[0].set_value("Replay").run()
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
    at.sidebar.radio[0].set_value("Replay").run()
    at.sidebar.radio[1].set_value("Any session (pick below)").run()
    assert not at.exception and not at.error, [e.value for e in at.exception]
    assert at.sidebar.selectbox(key="pw_round_2026").value == 20
    assert at.sidebar.selectbox(key="pw_sess_2026_20").value == 11396
    assert loaded == [11396]
    assert any("BOX" in m.value or "STAY OUT" in m.value for m in at.markdown)
