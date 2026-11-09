import pandas as pd

from f1analytics.pitwall import season as ss


def _res():
    rows = []
    for rnd, order in ((1, ["ANT", "HAM", "VER"]), (2, ["VER", "ANT", "HAM"]), (3, ["ANT", "VER", "HAM"])):
        for pos, code in enumerate(order, 1):
            rows.append({"round": rnd, "race": f"GP {rnd}", "code": code, "driver": code.title(), "family": code.title(),
                         "team": {"ANT": "Mercedes", "HAM": "Ferrari", "VER": "Red Bull"}[code], "grid": 4 - pos if rnd != 3 else (10 if code == "VER" else pos),
                         "position": pos, "text": str(pos), "points": [25, 18, 15][pos - 1], "status": "Finished", "fastest": pos == 1})
    return pd.DataFrame(rows)


def _ds():
    return pd.DataFrame([{"pos": 1, "code": "ANT", "driver": "Ant", "family": "Ant", "team": "Mercedes", "points": 68.0, "wins": 2},
                         {"pos": 2, "code": "VER", "driver": "Ver", "family": "Ver", "team": "Red Bull", "points": 58.0, "wins": 1},
                         {"pos": 3, "code": "HAM", "driver": "Ham", "family": "Ham", "team": "Ferrari", "points": 48.0, "wins": 0}])


def test_with_change_and_gap():
    before = _ds().assign(pos=[1, 3, 2])
    out = ss.with_change(_ds(), before, "code")
    assert list(out["gap"]) == [0, -10, -20]
    assert list(out["change"]) == [0, 1, -1]


def test_driver_card():
    card = ss.driver_card(_res(), _ds(), "HAM")
    assert card["pos"] == 3 and card["gap_ahead"] == -10 and card["ahead"] == "VER" and card["podiums"] == 3
    assert [t for _, t in card["last5"]] == ["2", "3", "3"]
    assert ss.driver_card(_res(), _ds(), "XXX") is None


def test_records_mention_climb_and_wins():
    texts = [t for _, t, _ in ss.records(_res(), _ds())]
    assert any("Ant leads the season with 2 wins" in t for t in texts)
    assert any("gained 8 places" in t for t in texts)


def test_progress_and_next_race():
    t = pd.Timestamp("2026-11-09T06:00:00Z")
    sched = [{"round": 20, "race_utc": pd.Timestamp("2026-11-08T17:00:00Z"), "sessions": []},
             {"round": 21, "race_utc": pd.Timestamp("2026-11-22T04:00:00Z"), "sessions": []}]
    assert ss.progress(sched, t) == (1, 2)
    assert ss.next_race(sched, t)["round"] == 21


def test_extras_totals_and_destructors():
    from f1analytics.ui import extras_pages as ep
    d = ep.load()
    tot = ep.upgrade_totals(d)
    assert tot.sum() == 476 and tot.index[0] == "McLaren" and tot["Ferrari"] == 52
    teams, drivers = ep.destructors_teams(d)
    assert teams.sum() == 27_468_000 and teams.index[0] == "Haas"
    assert list(teams.index).index("Ferrari") == 4 and drivers.iloc[0]["driver"] == "Bearman"


def test_extras_pages_render():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string("""
from f1analytics.ui import extras_pages as ep
ep.upgrades_page()
ep.destructors_page()
""").run(timeout=60)
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "476 new parts" in text and "Destructors" in text and "Ferrari are P5" in text
