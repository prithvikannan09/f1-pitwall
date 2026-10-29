import json
from pathlib import Path

import pytest

from f1analytics.live.recorder import read_current, record, replay_raw
from f1analytics.live.replay import RaceReplay, load_fixture
from f1analytics.live.state import LiveState, build_snapshot, merge, parse_gap, parse_time

FIX = Path(__file__).resolve().parent / "fixtures" / "live_state_usgp2026.json"
BUNDLED = Path(__file__).resolve().parent.parent / "f1analytics" / "replays" / "usgp2026"


@pytest.fixture(scope="module")
def live_state():
    return json.loads(FIX.read_text())


@pytest.fixture(scope="module")
def replay():
    return RaceReplay(load_fixture(BUNDLED))


def test_merge_rules():
    base = {"Lines": {"1": {"Position": "1", "Stints": [{"Compound": "SOFT"}]}}}
    out = merge(base, {"Lines": {"1": {"Position": "2", "Stints": {"0": {"TotalLaps": 5}, "1": {"Compound": "HARD"}}}}})
    line = out["Lines"]["1"]
    assert line["Position"] == "2"
    assert line["Stints"][0] == {"Compound": "SOFT", "TotalLaps": 5}
    assert line["Stints"][1]["Compound"] == "HARD"
    assert "2" not in merge({"a": {"2": 1, "3": 2}}, {"a": {"_deleted": ["2"]}})["a"]


def test_parsers():
    assert parse_gap("+1.234") == (1.234, 0)
    assert parse_gap("1L") == (None, 1)
    assert parse_gap("+2 LAPS") == (None, 2)
    assert parse_gap("LAP 56") == (0.0, 0)
    assert parse_gap("") == (None, 0)
    assert parse_time("1:38.321") == pytest.approx(98.321)
    assert parse_time("") is None


def test_snapshot_from_real_feed(live_state):
    snap = build_snapshot(live_state, [])
    assert snap["session"]["meeting"] == "United States Grand Prix"
    assert snap["session"]["total_laps"] == 56
    lec = next(d for d in snap["drivers"] if d["code"] == "LEC")
    assert lec["position"] == 2 and lec["gap_to_leader"] == pytest.approx(13.078)
    assert lec["compound"] == "HARD" and lec["tyre_age"] == 17 and lec["stint"] == 3
    assert lec["team"] == "Ferrari"
    leader = next(d for d in snap["drivers"] if d["position"] == 1)
    assert leader["gap_to_leader"] == 0.0
    assert len(snap["drivers"]) == 22


def _deltas():
    return [
        ("TimingData", {"Lines": {"16": {"NumberOfLaps": 57, "LastLapTime": {"Value": "1:38.500"}}}}),
        ("TrackStatus", {"Status": "4", "Message": "SCDeployed"}),
        ("TimingData", {"Lines": {"16": {"InPit": True}}}),
        ("TimingData", {"Lines": {"16": {"NumberOfLaps": 58, "LastLapTime": {"Value": "1:59.000"}}}}),
        ("TimingAppData", {"Lines": {"16": {"Stints": {"3": {"Compound": "SOFT", "TotalLaps": 0, "New": "true"}}}}}),
        ("TimingData", {"Lines": {"16": {"InPit": False, "PitOut": True}}}),
        ("TrackStatus", {"Status": "1", "Message": "AllClear"}),
        ("TimingData", {"Lines": {"16": {"PitOut": False, "NumberOfLaps": 59}}}),
        ("TimingData", {"Lines": {"16": {"LastLapTime": {"Value": "1:45.100"}}}}),
    ]


def test_lap_recording(live_state):
    ls = LiveState()
    ls.load_snapshot(live_state)
    for topic, delta in _deltas():
        ls.apply(topic, delta)
    laps = [r for r in ls.laps if r["number"] == "16"]
    assert [r["lap"] for r in laps] == [57, 58, 59]
    assert laps[0]["lap_time"] == pytest.approx(98.5) and laps[0]["track_status"] == "1"
    assert laps[1]["pit_in"] and laps[1]["track_status"] == "4"
    assert laps[2]["pit_out"] and laps[2]["compound"] == "SOFT"
    assert laps[2]["lap_time"] == pytest.approx(105.1)


def test_recorder_writes_and_replays(tmp_path, live_state):
    stream = [("__status__", {"connected": True}, None), ("__snapshot__", live_state, None)] + [(t, d, None) for t, d in _deltas()]
    record(tmp_path, stream=iter(stream))
    snap, age = read_current(tmp_path)
    assert snap["feed"]["connected"] and age < 60
    assert len([r for r in snap["laps"] if r["number"] == "16"]) == 3
    raw = next(tmp_path.glob("raw_*.jsonl"))
    rebuilt = replay_raw(raw)
    assert len(rebuilt.laps) == 3


def test_replay_matches_official_result(replay, live_state):
    final = replay.snapshot(replay.total_laps)
    order = [d["code"] for d in sorted(final["drivers"], key=lambda d: d["position"])][:5]
    live = build_snapshot(live_state, [])
    official = [d["code"] for d in sorted([d for d in live["drivers"] if d["position"]], key=lambda d: d["position"])][:5]
    assert order == official
    lec = next(d for d in final["drivers"] if d["code"] == "LEC")
    assert abs(lec["gap_to_leader"] - 13.078) < 0.5


def test_replay_laps_grow(replay):
    a, b = replay.snapshot(10), replay.snapshot(20)
    assert len(b["laps"]) > len(a["laps"])
    assert a["session"]["lap"] == 10
