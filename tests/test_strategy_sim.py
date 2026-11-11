import numpy as np
import pandas as pd

from f1analytics.pitwall import strategy_sim as ss


def _race(n=40, rain_from=30):
    """Dry race that turns wet: slicks lose 8s a lap once it rains, inters are 6s slower in the dry."""
    t0 = pd.Timestamp("2026-11-08T17:00:00Z")
    plans = {1: [("SOFT", 1, 15), ("MEDIUM", 16, rain_from - 1), ("INTERMEDIATE", rain_from, n)],
             2: [("MEDIUM", 1, 18), ("SOFT", 19, rain_from), ("INTERMEDIATE", rain_from + 1, n)],
             3: [("SOFT", 1, 14), ("HARD", 15, rain_from - 1), ("INTERMEDIATE", rain_from, n)],
             4: [("MEDIUM", 1, 20), ("SOFT", 21, rain_from - 1), ("INTERMEDIATE", rain_from, n)]}
    pace = {"SOFT": 0.0, "MEDIUM": 0.4, "HARD": 0.8, "INTERMEDIATE": 0.0}
    wear = {"SOFT": 0.1, "MEDIUM": 0.06, "HARD": 0.04, "INTERMEDIATE": 0.05}
    rows, stints = [], []
    for num, plan in plans.items():
        t = t0
        for i, (c, a, b) in enumerate(plan):
            stints.append({"driver_number": num, "stint_number": i + 1, "compound": c, "lap_start": a, "lap_end": b, "tyre_age_at_start": 0})
            for lap in range(a, b + 1):
                wet = lap >= rain_from
                base = 90.0 if wet else 80.0
                dur = base + pace[c] + wear[c] * (lap - a) + num * 0.1
                if wet and c != "INTERMEDIATE":
                    dur += 8.0
                if not wet and c == "INTERMEDIATE":
                    dur += 6.0
                pit_in = lap == b and i < len(plan) - 1
                pit_out = lap == a and i > 0
                dur += 20 if pit_in else 0
                dur += 5 if pit_out else 0
                rows.append({"driver_number": num, "lap_number": lap, "lap_duration": dur, "t": t, "compound": c, "tyre_age": lap - a,
                             "clean": lap > 1 and not pit_in and not pit_out, "pit_in": pit_in, "pit_out": pit_out, "neutral": False})
                t += pd.Timedelta(seconds=dur)
    return {"stints": pd.DataFrame(stints)}, pd.DataFrame(rows)


def test_track_state_spots_the_rain():
    raw, laps = _race()
    st = ss.track_state(raw, laps)
    assert set(st.loc[st.lap < 29, "cond"]) == {"dry"}
    assert set(st.loc[st.lap >= 31, "cond"]) == {"inter"}


def test_fit_measures_compound_gaps():
    raw, laps = _race()
    m = ss.fit(raw, laps)
    assert abs(m["delta"][("MEDIUM", "dry")] - 0.4) < 0.25
    assert m["delta"][("INTERMEDIATE", "inter")] == 0.0
    assert m["pace_src"][("WET", "wet")] == "estimate"
    assert 20 < m["pit_loss"] < 30


def test_optimiser_switches_to_inters_when_it_rains():
    raw, laps = _race()
    m = ss.fit(raw, laps)
    plans = ss.optimise(m)
    best = plans[0]
    assert best["compounds"][-1] == "INTERMEDIATE"
    assert abs(best["pits"][-1] - 29) <= 1
    assert ss.legal(best["compounds"])
    assert abs(ss.plan_time(m, best) - best["time"]) < 1e-6
    starts = ss.best_by_start(m)
    assert {p["compounds"][0] for p in starts} == set(ss.COMPOUNDS)
    assert starts[0]["time"] <= starts[-1]["time"]
    slick_only = {"compounds": ["SOFT", "MEDIUM"], "pits": [15]}
    assert ss.plan_time(m, slick_only) > best["time"] + 50


def test_legal_needs_two_dry_tyres_unless_wet():
    assert not ss.legal(["SOFT", "SOFT"])
    assert ss.legal(["SOFT", "MEDIUM"])
    assert ss.legal(["SOFT", "INTERMEDIATE"])


def test_rain_by_lap_maps_weather_to_laps():
    raw, laps = _race()
    t0 = laps.loc[laps.lap_number == 30, "t"].min()
    w = pd.DataFrame({"date": [(t0 - pd.Timedelta(minutes=40)).isoformat(), (t0 + pd.Timedelta(seconds=20)).isoformat()],
                      "rainfall": [0, 1], "track_temperature": [40.0, 25.0], "air_temperature": [20.0, 17.0]})
    r = ss.rain_by_lap(w, laps)
    naive = ss.rain_by_lap(w, laps.assign(t=laps["t"].dt.tz_localize(None)))
    assert naive["rain"].tolist() == r["rain"].tolist()
    assert bool(r.loc[r.lap == 30, "rain"].iloc[0]) and not bool(r.loc[r.lap == 5, "rain"].iloc[0])


def test_round_for_matches_upgrade_labels():
    from f1analytics.ui.performance_page import round_for

    rounds = [{"label": "Italy (Monza)"}, {"label": "Bahrain GP at Sepang"}, {"label": "Singapore"}, {"label": "São Paulo"}]
    assert round_for({"location": "São Paulo", "circuit": "Interlagos"}, rounds)["label"] == "São Paulo"
    assert round_for({"location": "Kuala Lumpur", "circuit": "Kuala Lumpur"}, rounds)["label"] == "Bahrain GP at Sepang"
    assert round_for({"location": "Marina Bay", "circuit": "Singapore"}, rounds)["label"] == "Singapore"
    assert round_for({"location": "Sakhir", "circuit": "Sakhir"}, rounds) is None


def test_performance_page_renders(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("F1_REVIEW_FETCH", "1")
    at = AppTest.from_string("""
import pandas as pd
import sys
sys.path.insert(0, "tests")
from test_strategy_sim import _race
from f1analytics.ui import performance_page as pp, review_panel

raw, laps = _race()
laps = laps.assign(date_start=laps["t"].astype(str), is_pit_out_lap=laps["pit_out"], st_speed=300.0,
                   duration_sector_1=25.0, duration_sector_2=30.0, duration_sector_3=25.0)
raw["laps"] = laps.drop(columns=["t", "compound", "tyre_age", "pit_in", "pit_out", "neutral", "clean"]).assign(session_key=1, meeting_key=1)
raw["drivers"] = pd.DataFrame({"driver_number": [1, 2, 3, 4], "name_acronym": ["NOR", "HAM", "LEC", "VER"],
                               "team_colour": ["FF8000", "E80020", "E80020", "3671C6"], "team_name": ["McLaren", "Ferrari", "Ferrari", "Red Bull Racing"]})
raw["pit"] = pd.DataFrame(columns=["driver_number", "lap_number", "pit_duration"])
raw["race_control"] = pd.DataFrame()
raw["session_result"] = pd.DataFrame({"driver_number": [1, 2, 3, 4], "position": [1, 2, 3, 4]})
raw["position"] = pd.DataFrame()
pp.races = lambda year=2026: [{"key": 99, "name": "São Paulo (Brazil)", "location": "São Paulo", "circuit": "Interlagos", "round": 21}]
review_panel.fetch = lambda sk: raw
pp.weather = lambda sk: pd.DataFrame(columns=["date", "rainfall", "track_temperature", "air_temperature"])
pp.page()
""").run(timeout=90)
    assert not at.exception
    tabs = [t.label for t in at.tabs]
    assert tabs[:3] == ["Upgrades & pace", "Tyre strategy & weather", "What if"]
    text = " ".join(m.value for m in at.markdown)
    assert "Upgrades brought to this race" in text and "Best tyre strategy" in text
    assert "What if they had skipped a pit stop?" in text
    assert not [w.value for w in at.warning]
    assert [b.label for b in at.selectbox][:3] == ["Race", "Driver", "Compare with"]
    assert "Time lost vs best plan" in text
