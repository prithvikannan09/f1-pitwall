from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from f1analytics.live.replay import load_fixture
from f1analytics.pitwall import review as rv

ROOT = Path(__file__).resolve().parent.parent
PAGE = str(ROOT / "pages" / "1_Pit_Wall.py")
USGP = ROOT / "f1analytics" / "replays" / "usgp2026"


@pytest.fixture(scope="module")
def us():
    raw = load_fixture(USGP)
    return raw, rv.lap_table(raw), {v: k for k, v in rv.codes(raw).items()}


def _synthetic():
    base = pd.Timestamp("2026-11-01T20:00:00Z")
    laps, t = [], {1: base, 2: base, 3: base}
    pace = {1: 80.0, 2: 80.3, 3: 81.0}
    for lap in range(1, 21):
        for n in (1, 2, 3):
            d = pace[n] + (5 if lap == 1 else 0) + 0.02 * lap
            if lap in (12, 13):
                d = 110.0
            if n == 1 and lap == 8:
                d += 6.3 + 20
            if n == 2 and lap == 8:
                d += 20
            laps.append({"driver_number": n, "lap_number": lap, "date_start": t[n].isoformat(), "lap_duration": d,
                         "duration_sector_1": d / 3, "duration_sector_2": d / 3, "duration_sector_3": d / 3,
                         "st_speed": 330 + n, "i1_speed": 300, "i2_speed": 290, "is_pit_out_lap": lap == 9})
            t[n] = t[n] + pd.Timedelta(seconds=d)
    stints = pd.DataFrame([
        {"driver_number": 1, "stint_number": 1, "compound": "SOFT", "lap_start": 1, "lap_end": 8, "tyre_age_at_start": 0},
        {"driver_number": 1, "stint_number": 2, "compound": "MEDIUM", "lap_start": 9, "lap_end": 20, "tyre_age_at_start": 0},
        {"driver_number": 2, "stint_number": 1, "compound": "MEDIUM", "lap_start": 1, "lap_end": 8, "tyre_age_at_start": 0},
        {"driver_number": 2, "stint_number": 2, "compound": "SOFT", "lap_start": 9, "lap_end": 20, "tyre_age_at_start": 3},
        {"driver_number": 3, "stint_number": 1, "compound": "HARD", "lap_start": 1, "lap_end": 20, "tyre_age_at_start": 0},
    ])
    pit = pd.DataFrame([{"driver_number": 1, "lap_number": 8, "pit_duration": 28.7}, {"driver_number": 2, "lap_number": 8, "pit_duration": 22.4}])
    rc = pd.DataFrame([
        {"lap_number": 1, "message": "TURN 4 INCIDENT INVOLVING CARS 3 (HAM) AND 1 (LEC) NOTED"},
        {"lap_number": 4, "message": "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 1 (LEC) - LEAVING THE TRACK AND GAINING AN ADVANTAGE"},
        {"lap_number": 10, "message": "FIA STEWARDS: PENALTY SERVED - 5 SECOND TIME PENALTY FOR CAR 1 (LEC)"},
        {"lap_number": 12, "message": "SAFETY CAR DEPLOYED"},
    ])
    drivers = pd.DataFrame([{"driver_number": 1, "name_acronym": "LEC", "team_name": "Ferrari", "team_colour": "E80020"},
                            {"driver_number": 2, "name_acronym": "VER", "team_name": "Red Bull Racing", "team_colour": "3671C6"},
                            {"driver_number": 3, "name_acronym": "HAM", "team_name": "Ferrari", "team_colour": "E80020"}])
    return {"laps": pd.DataFrame(laps), "stints": stints, "pit": pit, "race_control": rc, "drivers": drivers}


def test_clean_laps_skip_lap1_pits_and_safety_car():
    raw = _synthetic()
    laps = rv.lap_table(raw)
    lec = laps[laps["driver_number"] == 1].set_index("lap_number")
    assert not lec.loc[1, "clean"] and not lec.loc[8, "clean"] and not lec.loc[9, "clean"]
    assert not lec.loc[12, "clean"] and not lec.loc[13, "clean"] and not lec.loc[14, "clean"]
    assert lec.loc[5, "clean"] and lec.loc[15, "clean"]
    assert rv.green_windows(laps) == [(2, 11), (15, 20)]


def test_phases_split_on_own_stop_and_neutral():
    laps = rv.lap_table(_synthetic())
    assert rv.phases(laps, 1) == [(2, 7), (15, 20)]


def test_tyre_state_new_and_used():
    laps = rv.lap_table(_synthetic())
    ver = rv.tyre_state(laps, 2, 10)
    assert ver["compound"] == "SOFT" and not ver["new_set"] and ver["tyre_age"] == 4
    assert rv.tyre_edge(rv.tyre_state(laps, 1, 15), rv.tyre_state(laps, 2, 15)) == "rival on the softer tyre, your tyres 3 laps fresher"


def test_pace_by_phase_gap_sign():
    laps = rv.lap_table(_synthetic())
    p = rv.pace_by_phase(laps, 1, [2, 3])
    first = p[(p["start"] == 2) & (p["driver_number"] == 2)].iloc[0]
    assert first["gap"] == pytest.approx(0.3, abs=1e-6)
    assert "New S" in p[(p["start"] == 2) & (p["driver_number"] == 1)].iloc[0]["tyre"]


def test_stop_with_penalty_and_cost():
    raw = _synthetic()
    laps = rv.lap_table(raw)
    s = rv.stops(raw, laps, 1)[0]
    assert s["penalty"] == 5 and s["condition"] == "Green flag"
    assert s["extra"] == pytest.approx(28.7 - 25.55, abs=0.01)
    assert s["from"].startswith("New S") and s["to"].startswith("New M")
    assert rv.strategy(laps, 2)[1] == {"compound": "SOFT", "short": "S", "new": False, "age_start": 3, "start": 9, "end": 20}


def test_stop_cost_lists_rivals_within_the_extra_time():
    raw = _synthetic()
    raw["pit"].loc[raw["pit"]["driver_number"] == 2, "pit_duration"] = 22.4
    laps = rv.lap_table(raw)
    s = dict(rv.stops(raw, laps, 1)[0], extra=12.0)
    lost = rv.stop_cost(laps, 1, s)
    assert [n for n, _ in lost] == [2]


def test_penalties_and_moments():
    raw = _synthetic()
    pens = rv.penalties(raw)
    assert list(pens["seconds"]) == [5, 5] and list(pens["served"]) == [False, True]
    m = rv.moments(raw, 1)
    assert m[0]["mine"] and "TURN 4" in m[0]["message"]
    assert any("SAFETY CAR" in x["message"] and not x["mine"] for x in m)
    assert not any(x["mine"] for x in rv.moments(raw, 2))


def test_weekend_sets_count_new_sets():
    ws = pd.DataFrame([
        {"session_key": 1, "driver_number": 44, "compound": "SOFT", "tyre_age_at_start": 0},
        {"session_key": 1, "driver_number": 44, "compound": "SOFT", "tyre_age_at_start": 4},
        {"session_key": 2, "driver_number": 44, "compound": "SOFT", "tyre_age_at_start": 0},
        {"session_key": 2, "driver_number": 44, "compound": "HARD", "tyre_age_at_start": 0},
        {"session_key": 9, "driver_number": 44, "compound": "MEDIUM", "tyre_age_at_start": 0},
        {"session_key": 9, "driver_number": 44, "compound": "INTERMEDIATE", "tyre_age_at_start": 0},
    ])
    s = rv.weekend_sets(ws, 9).loc[44]
    assert s["SOFT_before"] == 2 and s["SOFT_left"] == 6 and s["HARD_left"] == 1 and s["MEDIUM_race"] == 1 and s["MEDIUM_left"] == 3
    assert rv.weekend_sets(ws, 9, sprint=True).loc[44]["SOFT_left"] == 4


def test_real_race_us_gp(us):
    raw, laps, num = us
    ham = num["HAM"]
    wins = rv.green_windows(laps)
    assert wins and all(b >= a for a, b in wins)
    p = rv.pace_by_phase(laps, ham, rv.default_rivals(raw, laps, ham))
    assert not p.empty and p["median"].dropna().between(90, 110).all()
    strat = rv.strategy(laps, ham)
    assert [s["short"] for s in strat] == ["S", "M", "H"] and not strat[0]["new"]
    st = rv.stops(raw, laps, ham)
    assert [s["lap"] for s in st] == [14, 38] and all(abs(s["extra"]) < 2 for s in st)
    rus = rv.stops(raw, laps, num["RUS"])
    assert any(s["penalty"] == 5 for s in rus)
    assert not rv.sectors(laps, [ham, num["LEC"]]).empty


def test_review_section_renders_in_past_races():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    at.radio(key="pw_mode").set_value("Past races").run()
    assert not at.exception and not at.error
    heads = [h.value for h in at.subheader]
    assert "Race review" in heads
    focus = next(s for s in at.selectbox if s.key and s.key.startswith("rv_focus_"))
    assert focus.value is not None
    text = " ".join(m.value for m in at.markdown)
    assert "Laps " in text
    names = [t.label for t in at.tabs]
    assert names[:6] == ["Head to head", "Pace & tyres", "Pit strategy", "Track sectors", "Positions", "Tyre sets"]
