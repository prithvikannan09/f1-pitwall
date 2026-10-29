from pathlib import Path

import pytest

from f1analytics.live.replay import RaceReplay, load_fixture
from f1analytics.pitwall.engine import analyse, compound_table, laps_frame, plan_options, rejoin
from f1analytics.pitwall.tracks import COMPOUND_PRIORS, pit_loss_for

BUNDLED = Path(__file__).resolve().parent.parent / "f1analytics" / "replays" / "usgp2026"


@pytest.fixture(scope="module")
def replay():
    return RaceReplay(load_fixture(BUNDLED))


def _table():
    return {c: {"alpha": 90 + v["offset"], "beta": v["deg"], "source": "estimate"} for c, v in COMPOUND_PRIORS.items()}


def test_track_pit_loss():
    assert pit_loss_for("Mexico City") == (22.5, True)
    assert pit_loss_for("Austin") == (20.5, True)
    assert pit_loss_for("Nowhere")[1] is False


def test_two_compound_rule_forces_stop():
    plans = plan_options(_table(), "MEDIUM", 5, 40, 22.0, ["MEDIUM"])
    assert (plans["stops"] > 0).all()
    plans2 = plan_options(_table(), "HARD", 5, 40, 22.0, ["MEDIUM", "HARD"])
    assert (plans2["stops"] == 0).any()


def test_short_run_to_flag_needs_no_stop():
    best = plan_options(_table(), "HARD", 20, 5, 22.0, ["MEDIUM", "HARD"]).iloc[0]
    assert best["stops"] == 0


def test_rejoin_math():
    snap = {"drivers": [
        {"number": "1", "code": "AAA", "position": 1, "gap_to_leader": 0.0, "compound": "M", "tyre_age": 5},
        {"number": "2", "code": "BBB", "position": 2, "gap_to_leader": 3.0, "compound": "M", "tyre_age": 5},
        {"number": "3", "code": "CCC", "position": 3, "gap_to_leader": 20.0, "compound": "M", "tyre_age": 5},
        {"number": "4", "code": "DDD", "position": 4, "gap_to_leader": 25.5, "compound": "M", "tyre_age": 5},
    ]}
    rj = rejoin(snap, snap["drivers"][1], 22.0)
    assert rj["position"] == 3 and rj["car_ahead"] == "CCC"
    assert rj["gap_ahead"] == pytest.approx(5.0) and rj["car_behind"] == "DDD" and rj["gap_behind"] == pytest.approx(0.5)
    tight = rejoin(snap, snap["drivers"][1], 17.5)
    assert tight["traffic"]


def test_engine_matches_ferrari_first_stop(replay):
    res = analyse(replay.snapshot(14))
    lec = next(r for r in res["cars"] if r["car"]["code"] == "LEC")
    assert lec["call"] == "BOX THIS LAP"
    assert 18 < res["pit_loss"] < 25
    late = analyse(replay.snapshot(30))
    assert late["pit_loss_source"].startswith("measured")
    assert 19 < late["pit_loss"] < 23


def test_engine_no_more_stops_late(replay):
    res = analyse(replay.snapshot(45))
    for r in res["cars"]:
        assert r["call"] == "STAY OUT"
        assert r["best_plan"]["stops"] == 0
        assert not r["safety_car"]["SC"]["box"]
        if r["attack"]:
            assert r["attack"]["probability"] is None


def test_engine_sc_and_double_stack(replay):
    snap = replay.snapshot(8)
    snap["session"]["track_status"] = "4"
    res = analyse(snap)
    assert res["neutralised"] == "SC"
    assert all(r["safety_car"]["SC"]["box"] for r in res["cars"])
    ds = res["cars"][0]["double_stack"]
    assert ds and ds["first"] == "LEC"


def test_laps_frame_flags(replay):
    df = laps_frame(replay.snapshot(20))
    assert df["IsAccurate"].sum() > 0
    assert not df.loc[df["PitInTime"].notna(), "IsAccurate"].any()
    table, _ = compound_table(df, 56)
    assert set(["SOFT", "MEDIUM", "HARD"]) <= set(table)


def test_car_profile_and_practice(replay):
    from f1analytics.live.replay import SessionReplay
    from f1analytics.pitwall.car import mode_hints, practice_summary, speed_profile

    sp = speed_profile(replay.snapshot(40), "HAM", "LEC")
    assert sp and sp["cars"] == 22 and "wing" in sp["level"]
    assert isinstance(mode_hints(replay.snapshot(40), "HAM"), list)
    fp = SessionReplay(load_fixture(BUNDLED.parent / "mex2025_fp2"))
    snap = fp.snapshot_at(fp.duration_s)
    summary = practice_summary(snap, "Ferrari", "HAM")
    assert [c["car"]["code"] for c in summary["cars"]][0] == "HAM"
    assert summary["cars"][0]["runs"] and len(summary["wear"])
    lec = next(d for d in snap["drivers"] if d["code"] == "LEC")
    assert lec["position"] == 2 and abs(lec["best_lap"] - 77.545) < 1e-6
