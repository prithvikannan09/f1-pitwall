from f1analytics import config
from f1analytics.analysis.laps import (
    clean_laps, estimate_pit_loss, fastest_lap_per_driver, neutralised, race_gaps, speed_trap,
)
from f1analytics.sources import SessionKey


def test_clean_laps_drops_bad_laps(synthetic_race):
    clean = clean_laps(synthetic_race.laps)
    assert clean["PitInTime"].isna().all() and clean["PitOutTime"].isna().all()
    assert not neutralised(clean["TrackStatus"]).any()
    assert clean["IsAccurate"].all()
    assert (clean["LapNumber"] > 1).all()


def test_clean_laps_removes_safety_car(source):
    for gp in ("Mexico", "Bahrain", "Monza", "Spa", "Monaco", "Japan"):
        sd = source.load(SessionKey(2024, gp, "R"))
        if neutralised(sd.laps["TrackStatus"]).any():
            assert not neutralised(clean_laps(sd.laps)["TrackStatus"]).any()
            return
    raise AssertionError("no sample race had a Safety Car to test against")


def test_speed_trap_uses_max_reading(synthetic_quali):
    laps = synthetic_quali.laps
    st = speed_trap(laps).set_index("Driver")["SpeedST"]
    expected = laps.groupby("Driver")["SpeedST"].max()
    assert (st.sort_index() == expected.sort_index()).all()
    fastest = fastest_lap_per_driver(laps).set_index("Driver")["SpeedST"]
    assert (st.reindex(fastest.index) > fastest).any()


def test_pit_loss_estimate(synthetic_race):
    truth = 22.0 + config.WARMUP_PENALTY_S
    assert abs(estimate_pit_loss(synthetic_race.laps) - truth) < 1.5


def test_no_function_mutates_input(synthetic_race):
    laps = synthetic_race.laps
    before = laps.copy()
    clean_laps(laps)
    speed_trap(laps)
    fastest_lap_per_driver(laps)
    race_gaps(laps, "VER")
    estimate_pit_loss(laps)
    assert laps.equals(before)


def test_race_gaps_reference_is_zero(synthetic_race):
    gaps = race_gaps(synthetic_race.laps, "VER")
    assert gaps["VER"].abs().max() == 0
