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
pp.season_results = lambda year=2026: pd.DataFrame([{"round": r, "code": c, "driver": c, "team": "T", "position": p, "text": str(p), "points": 26 - p}
                                                    for r in range(1, 9) for p, c in enumerate(["NOR", "HAM", "LEC", "VER"], 1)])
pp.page()
""").run(timeout=90)
    assert not at.exception
    tabs = [t.label for t in at.tabs]
    assert tabs[:4] == ["Upgrades & pace", "Tyre strategy & weather", "What if", "Season: driver form"]
    text = " ".join(m.value for m in at.markdown)
    assert "Race pace by team" in text and "Best tyre strategy" in text
    assert "What if they had skipped a pit stop?" in text
    assert not [w.value for w in at.warning if "telemetry" not in w.value]
    assert "Upgrades at this race and did they work?" in text and "Telemetry at São Paulo: HAM vs LEC" in text
    assert [b.label for b in at.selectbox][:3] == ["Race", "Driver", "Compare with"]
    assert "Time lost vs best plan" in text
    assert "Who started strong and who faded" in text


def test_latest_upgrades_lists_every_team():
    from f1analytics.ui import extras_pages
    from f1analytics.ui.performance_page import latest_upgrades

    d = extras_pages.load()
    rows = latest_upgrades(d)
    assert len(rows) == len(d["upgrades"]["teams"])
    mcl = next(r for r in rows if r["team"] == "McLaren")
    assert mcl["round"] == "São Paulo" and len(mcl["parts"]) == 4
    fer = next(r for r in rows if r["team"] == "Ferrari")
    assert fer["round"] != "São Paulo" and fer["total"] == 52


def test_history_has_every_round_for_a_team():
    from f1analytics.ui import extras_pages
    from f1analytics.ui.performance_page import history

    d = extras_pages.load()
    h = history(d, "Ferrari")
    assert sum(x["count"] for x in h) == 52
    assert h[0]["round"] == "Mexico City" and h[-1]["round"] == "Australia to Dutch GP"


def test_season_upgrades_vs_pace():
    from f1analytics.pitwall import season_form as sf
    from f1analytics.pitwall.racecraft import load
    from f1analytics.ui import extras_pages

    data = load()
    pace = sf.team_pace(data)
    assert set(pace.groupby("race")["gap"].min().round(6)) == {0.0}
    assert "Red Bull" in set(pace["team"]) and "Haas" in set(pace["team"])
    ev = sf.upgrade_events(extras_pages.load(), data["races"])
    monza = next(i for i, r in enumerate(data["races"]) if r["location"] == "Monza")
    assert set(ev.loc[ev["label"] == "Italy (Monza)", "race"]) == {monza}
    assert ev.loc[ev["label"] == "Australia to Dutch GP", "race"].isna().all()
    v = sf.verdicts(pace, ev)
    assert int(v.loc[v["team"] == "Ferrari", "parts"].iloc[0]) == 52
    fx = sf.event_effect(pace, ev, "McLaren")
    assert fx[-1]["label"] == "São Paulo"


def test_driver_form_spots_fade_and_rise():
    from f1analytics.pitwall import season_form as sf

    rows = []
    for rnd in range(1, 11):
        rows.append({"round": rnd, "code": "AAA", "driver": "A", "team": "T1", "position": 1 if rnd <= 5 else 12, "text": "1" if rnd <= 5 else "12",
                     "points": 25 if rnd <= 5 else 0})
        rows.append({"round": rnd, "code": "BBB", "driver": "B", "team": "T2", "position": 12 if rnd <= 5 else 1, "text": "12" if rnd <= 5 else "1",
                     "points": 0 if rnd <= 5 else 25})
        rows.append({"round": rnd, "code": "CCC", "driver": "C", "team": "T3", "position": 5, "text": "5" if rnd != 3 else "R", "points": 10})
    f = sf.driver_form(pd.DataFrame(rows)).set_index("code")
    assert f.loc["AAA", "form"] == "Started strong, faded" and f.loc["BBB", "form"] == "Finishing strong" and f.loc["CCC", "form"] == "Steady"
    assert f.loc["CCC", "dnf_first"] == 1 and f.attrs["half"] == 5
    cum = sf.cumulative_points(pd.DataFrame(rows))
    assert cum.loc[10, "AAA"] == 125


def test_pu_parser_and_tables():
    from f1analytics.pitwall import pu_elements as pu

    text = """                    2026 SÃO PAULO GRAND PRIX
To         The Stewards                                     Date       06 November 2026
                                                            Time       08:34
81     McLaren Mercedes               Oscar Piastri         4    3     3      2   3     3     5
i      Aston Martin Aramco Honda      Lance Stroll          6    7     3      5   8     7     9
"""
    p = pu.parse_text(text)
    assert p["date"] == "06 November 2026" and p["time"] == "08:34" and len(p["rows"]) == 2
    assert p["rows"][1]["number"] is None and p["rows"][1]["ES"] == 8
    data = pu.load()
    assert data["events"][-1]["label"] == "São Paulo" and all(len(e["rows"]) == 22 for e in data["events"])
    ev, df = pu.table(data)
    ham = df[df["driver"] == "Lewis Hamilton"].iloc[0]
    assert ham["ICE"] == 4 and ham["TC"] == 4
    over = pu.over_limit(df)
    assert over["Isack Hadjar"]["ICE"] == 4 and "Lewis Hamilton" not in over
    h = pu.history(data, "Lewis Hamilton")
    assert h["ICE"].is_monotonic_increasing and h["event"].iloc[0] == "China"


def test_upgrades_page_renders():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_string("""
from f1analytics.ui import upgrades_page
upgrades_page.page()
""").run(timeout=90)
    assert not at.exception
    assert [t.label for t in at.tabs][:3] == ["Car parts", "Engine components", "Did the upgrades work?"]
    text = " ".join(m.value for m in at.markdown)
    assert "476 new parts" in text and "Engine parts used this season" in text and "Over the limit" in text and "Did the upgrades work?" in text


def test_upgrade_impact_at_a_race():
    from f1analytics.pitwall import season_form as sf
    from f1analytics.pitwall.racecraft import load
    from f1analytics.ui import extras_pages

    data = load()
    ev = sf.upgrade_events(extras_pages.load(), data["races"])
    austin = next(i for i, r in enumerate(data["races"]) if r["location"] == "Austin")
    rows = {x["team"]: x for x in sf.impact_at(data, ev, austin)}
    assert "Ferrari" in rows and rows["Ferrari"]["parts"] == 4
    f = rows["Ferrari"]
    assert f["pace_before"] is not None and f["pace_after"] is not None and f["races_after"] >= 2
    assert "top_speed_kmh_before" in f
    assert sf.race_index(data, data["races"][3]["session_key"]) == 3
