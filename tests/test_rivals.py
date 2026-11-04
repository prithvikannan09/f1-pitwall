from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from f1analytics.pitwall import rivalry as rv

PAGE = str(Path(__file__).resolve().parent.parent / "pages" / "1_Pit_Wall.py")


def _row(y, k, s, c, p, team="T", dnf=False, dsq=False, loc="X"):
    return {"y": y, "loc": loc, "d": f"{y}-0{1 + k % 9}-01", "s": s, "k": k, "c": c, "t": team, "p": p, "dnf": dnf, "dns": False, "dsq": dsq}


def _df():
    rows = [
        _row(2025, 1, "Race", "HAM", 1, "Ferrari"), _row(2025, 1, "Race", "LEC", 2, "Ferrari"),
        _row(2025, 2, "Race", "HAM", None, "Ferrari", dnf=True), _row(2025, 2, "Race", "LEC", 5, "Ferrari"),
        _row(2025, 3, "Race", "HAM", None, "Ferrari", dnf=True), _row(2025, 3, "Race", "LEC", None, "Ferrari", dnf=True),
        _row(2025, 4, "Race", "HAM", 3, "Ferrari"), _row(2025, 4, "Race", "LEC", 2, "Ferrari"),
        _row(2025, 5, "Qualifying", "HAM", 4, "Ferrari"), _row(2025, 5, "Qualifying", "LEC", 1, "Ferrari"),
        _row(2026, 6, "Race", "HAM", 8, "Ferrari"), _row(2026, 6, "Race", "LEC", 4, "Ferrari", dsq=True),
        _row(2026, 6, "Race", "VER", 1, "Red Bull Racing"),
    ]
    return pd.DataFrame(rows)


def test_head_to_head_counts_retirements_as_behind_and_skips_double_dnf():
    h = rv.head_to_head(_df(), "HAM", "LEC")
    assert (h["n"], h["a"], h["b"]) == (4, 2, 2)
    assert h["both_fin"] == 2 and h["podiums"] == 2
    assert h["avg_gap"] == pytest.approx(0.0)


def test_qualifying_and_years_filter():
    assert rv.head_to_head(_df(), "HAM", "LEC", "Qualifying")["b"] == 1
    h = rv.head_to_head(_df(), "HAM", "LEC", years=[2026])
    assert (h["n"], h["a"], h["b"]) == (1, 1, 0)
    assert rv.head_to_head(_df(), "HAM", "XXX")["n"] == 0


def test_by_season_marks_teammates():
    s = rv.by_season(_df(), "HAM", "LEC")
    assert [x["year"] for x in s] == [2025, 2026] and all(x["teammates"] for x in s)
    assert s[0]["race"] == (1, 2)
    assert rv.by_season(_df(), "HAM", "VER")[0]["teammates"] is False


def test_season_record():
    assert rv.season_record(_df(), "HAM") == {"starts": 5, "wins": 1, "podiums": 2, "dnfs": 2}


def test_track_table_rates_and_spots():
    races = pd.DataFrame([{"y": 2025, "loc": "A", "k": 1, "ck": 1, "laps": 50, "green": 40, "passes": 80},
                          {"y": 2026, "loc": "A", "k": 2, "ck": 1, "laps": 50, "green": 50, "passes": 50},
                          {"y": 2026, "loc": "B", "k": 3, "ck": 2, "laps": 70, "green": 60, "passes": 6},
                          {"y": 2026, "loc": "C", "k": 4, "ck": 3, "laps": 50, "green": 50, "passes": 0}])
    passes = pd.DataFrame([{"y": 2025, "loc": "A", "k": 1, "by": 1, "on": 2, "corner": 1}] * 30 + [{"y": 2025, "loc": "A", "k": 1, "by": 1, "on": 2, "corner": 4}] * 10
                          + [{"y": 2026, "loc": "B", "k": 3, "by": 1, "on": 2, "corner": 7}] * 6)
    t = rv.track_table(races, passes)
    assert list(t.index) == ["A", "B"]
    assert t.loc["A", "per10"] == pytest.approx(15.0)
    assert t.loc["A", "spots"].startswith("T1 75%")
    assert t.loc["B", "spots"] == "too few passes to place"
    assert rv.corners(passes, "A")[0] == (1, 0.75)


def test_year_change():
    races = pd.DataFrame([{"y": 2025, "loc": "A", "k": 1, "passes": 10}, {"y": 2026, "loc": "A", "k": 2, "passes": 30},
                          {"y": 2025, "loc": "B", "k": 3, "passes": 20}, {"y": 2026, "loc": "B", "k": 4, "passes": 10},
                          {"y": 2026, "loc": "C", "k": 5, "passes": 99}])
    c = rv.year_change(races)
    assert (c["tracks"], c["before"], c["after"], c["up"]) == (2, 30, 40, 1)


def test_nearest_corner_wraps_round_the_lap():
    assert rv.nearest_corner(0.99, [(1, 0.02), (2, 0.5)]) == 1
    assert rv.nearest_corner(0.45, [(1, 0.02), (2, 0.5)]) == 2


def test_committed_data_loads_and_matches_known_records():
    df = rv.load_results()
    races, passes = rv.load_overtakes()
    assert not df.empty and not races.empty
    h = rv.head_to_head(df, "VER", "PER", "Qualifying", [2023, 2024])
    assert h["a"] > 35 and h["b"] < 5
    assert rv.season_record(df, "VER", [2023])["wins"] == 19
    t = rv.track_table(races, passes)
    assert t.loc["Monaco", "per10"] < t.loc["Baku", "per10"]


def test_rivals_view_renders():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.query_params["mode"] = "rivals"
    at.run()
    assert not at.exception and not at.error
    heads = [h.value for h in at.subheader]
    assert "Rivalries: head to head" in heads and "Where can you overtake?" in heads
    assert at.selectbox(key="rv_a").value == "HAM" and at.selectbox(key="rv_b").value == "VER"
    text = " ".join(m.value for m in at.markdown)
    assert "HAM 21 – 67 VER" in text
    at.selectbox(key="rv_b").set_value("LEC").run()
    assert not at.exception
    assert "HAM 32 – 52 LEC" in " ".join(m.value for m in at.markdown)
    at.selectbox(key="ot_track").set_value("Baku").run()
    assert not at.exception


def test_teammate_and_young_drivers():
    df = _df()
    assert rv.teammate(df, "HAM", 2025) == ("LEC", "Ferrari")
    assert rv.teammate(df, "VER", 2026) == (None, "Red Bull Racing")
    rows = rv.young_drivers(df, 2025, [("LEC", "test")])
    assert rows[0]["mate"] == "HAM" and rows[0]["race"] == (2, 1) and rows[0]["starts"] == 4
    assert rv.young_drivers(df, 2025, [("XXX", "none")]) == []


def test_young_drivers_from_real_data():
    rows = {x["code"]: x for x in rv.young_drivers(rv.load_results(), 2026)}
    assert rows["LIN"]["team"] == "Racing Bulls" and rows["LIN"]["mate"] == "LAW"
    assert rows["ANT"]["wins"] >= 9


def test_storylines_render():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.query_params["mode"] = "rivals"
    at.run()
    assert not at.exception
    assert "2026 storylines" in [h.value for h in at.subheader]
    labels = [e.label for e in at.expander]
    assert "Mercedes' engine loophole" in labels and "Mexico: Ferrari vs Ferrari" in labels


def test_all_drivers_and_form():
    df = _df()
    rows = {r["code"]: r for r in rv.all_drivers(df, 2025, min_races=1)}
    assert rows["LEC"]["avg_quali"] == 1.0 and rows["HAM"]["wins"] == 1 and rows["HAM"]["dnfs"] == 2
    assert rows["LEC"]["beat_mate_quali"] == 1.0
    assert [f["year"] for f in rv.form_by_season(df, "HAM")] == [2025, 2026]


def test_hamilton_2026_from_real_data():
    df = rv.load_results()
    ham = next(r for r in rv.all_drivers(df, 2026) if r["code"] == "HAM")
    assert ham["poles"] >= 1 and ham["avg_quali"] < 6


def test_compare_all_renders():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.query_params["mode"] = "rivals"
    at.run()
    assert not at.exception
    assert "All drivers compared" in [h.value for h in at.subheader]
    assert at.selectbox(key="cmp_driver").value == "HAM"
    assert "averages" in " ".join(m.value for m in at.markdown)
