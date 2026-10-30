import numpy as np
import pandas as pd
import pytest

from f1analytics.live.replay import RaceReplay, load_fixture
from f1analytics.pitwall import racecraft as rc
from f1analytics.pitwall.engine import start_tyre_options

from pathlib import Path

BUNDLED = Path(__file__).resolve().parent.parent / "f1analytics" / "replays" / "usgp2026"


def _rows():
    rng = np.random.default_rng(1)
    rows = []
    for race in range(6):
        for i, code in enumerate(["HAM", "LEC", "VER", "HAD", "NOR", "PIA", "RUS", "ANT"]):
            team = {"HAM": "Ferrari", "LEC": "Ferrari", "VER": "Red Bull Racing", "HAD": "Red Bull Racing"}.get(code, "Other" + str(i // 2))
            rows.append({"session_key": race, "number": i, "code": code, "team": team,
                         "attack_laps": 20, "pressure_laps": 20,
                         "passes_made": 6 if code == "HAM" else 2, "passes_lost": 0 if code == "VER" else 3,
                         "lap1_gain": 2.0 if code == "LEC" else 0.0, "wear_rel": 0.0, "pace_pct": 0.2 * i,
                         "grid": i + 1, "finish": i + 1, "start_tyre": "MEDIUM" if i % 2 else "SOFT",
                         "brake_later_m": 12.0 if code == "HAM" else rng.normal(0, 3), "late_straight_acc": 1.5 if code == "VER" else rng.normal(0, .2),
                         "top_speed_kmh": 0.0, "corner_speed_kmh": 0.0, "clip_kmh": 0.0})
    return rows


def test_season_profiles_and_tags():
    prof = rc.build_season(_rows())
    ham, ver, lec = prof["HAM"], prof["VER"], prof["LEC"]
    assert ham["attack_score"] >= 90 and ver["defence_score"] >= 90
    names = {t["name"] for t in ham["tags"]}
    assert "Hunter" in names and "Late braker" in names
    assert "Strong on the straights" in {t["name"] for t in ver["tags"]}
    assert "Rocket starts" in {t["name"] for t in lec["tags"]}
    assert ham["teammate"] == "LEC" and ham["brake_later_m_vs_mate"] > 5
    assert 0 < ham["attack_conv"] < 1 and 0 < ver["defence_hold"] <= 1


def test_start_tyre_stats():
    stats = rc.start_tyre_stats(_rows())
    assert set(stats) == {"SOFT", "MEDIUM"} and stats["SOFT"]["starts"] == 24


def test_head_to_head_today_and_season():
    prof = rc.build_season(_rows())
    rep = RaceReplay(load_fixture(BUNDLED))
    today = rc.head_to_head(rep.snapshot(30), prof, "HAM", "VER")
    assert today["source"] == "today" and 0 <= today["prob"] <= 1 and today["reasons"]
    pre = rc.head_to_head({"session": {"type": "Practice"}}, prof, "HAM", "VER")
    assert pre["source"] == "season" and 0 <= pre["prob"] <= 1
    ham_fast = rc.head_to_head({"session": {"type": "Practice"}}, prof, "HAM", "ANT")
    ant_fast = rc.head_to_head({"session": {"type": "Practice"}}, prof, "ANT", "HAM")
    assert ham_fast["prob"] > 0.5 > ant_fast["prob"]


def test_racecraft_holds_off_faster_car():
    prof = rc.build_season(_rows())
    wall = dict(prof["VER"], defence_hold=0.999, attack_conv=0.01)
    leaky = dict(prof["VER"], defence_hold=0.5, attack_conv=0.01)
    hunter = dict(prof["HAM"], attack_conv=0.3)
    snapless = {"session": {"type": "Practice", "total_laps": 50}}
    p_wall = rc.head_to_head(snapless, dict(prof, VER=wall, HAM=hunter), "HAM", "VER")
    p_leak = rc.head_to_head(snapless, dict(prof, VER=leaky, HAM=hunter), "HAM", "VER")
    assert p_wall["prob"] <= p_leak["prob"] + 1e-9


def test_start_tyre_options_cover_all_dry():
    rep = RaceReplay(load_fixture(BUNDLED))
    res = start_tyre_options(rep.snapshot(1))
    assert res["laps"] == 56 and {o["compound"] for o in res["options"]} == {"SOFT", "MEDIUM", "HARD"}
    assert res["options"][0]["delta"] == 0
    for o in res["options"]:
        assert o["stops"] >= 1


def test_brake_zone_and_straight_detection():
    t = np.arange(0, 30, 0.25)
    v = np.where(t < 8, 200 + 12 * t, np.where(t < 10, 296 - 100 * (t - 8), 96 + 10 * (t - 10)))
    tr = pd.DataFrame({"s": t, "v": v, "d": np.concatenate([[0], np.cumsum((v[1:] + v[:-1]) / 2 / 3.6 * 0.25)]),
                       "thr": np.where((t < 8) | (t > 11), 100, 0), "brk": (t >= 8) & (t < 10)})
    zones = rc._brake_zones(tr)
    assert len(zones) == 1 and zones[0]["v0"] > 280 and zones[0]["vmin"] < 110
    straights = rc._straights(tr)
    assert straights and straights[0]["top"] >= 290


def test_track_affinity_finds_best_and_bogey():
    rows = []
    for year in (2024, 2025):
        for loc, ham, lec in (("Silverstone", 0.0, 0.6), ("Monza", 0.5, 0.2), ("Suzuka", 0.3, 0.3), ("Spa", 0.3, 0.3), ("Lusail", 0.9, 0.2)):
            rows.append({"year": year, "location": loc, "code": "HAM", "team": "Ferrari", "pace_pct": ham, "finish": 1, "grid": 1})
            rows.append({"year": year, "location": loc, "code": "LEC", "team": "Ferrari", "pace_pct": lec, "finish": 2, "grid": 2})
    aff = rc.track_affinity(rows)
    assert aff["HAM"]["best"][0]["location"] == "Silverstone"
    assert aff["HAM"]["worst"][0]["location"] == "Lusail"
    assert rc.affinity_at(aff, "HAM", "silverstone")["visits"] == 2


def test_real_data_files_load():
    data = rc.load(2026)
    if data is None:
        pytest.skip("no built data")
    assert len(data["profiles"]) >= 20
    hist = rc.load_history()
    assert hist and len(hist["rows"]) > 500


def test_styles_on_page():
    from streamlit.testing.v1 import AppTest

    page = str(Path(__file__).resolve().parent.parent / "pages" / "1_Pit_Wall.py")
    at = AppTest.from_file(page, default_timeout=120)
    at.run()
    at.sidebar.radio[0].set_value("Replay").run()
    at.slider(key="pw_lap").set_value(30).run()
    assert not at.exception and not at.error
    text = " ".join(m.value for m in at.markdown)
    assert "Chance HAM finishes ahead of" in text and "Strongest tracks" in text and "At Austin" in text
    at.selectbox(key="sty_rival_HAM").set_value("VER").run()
    assert "Chance HAM finishes ahead of VER" in " ".join(m.value for m in at.markdown)
    at.sidebar.radio[1].set_value("2025 Mexico · Practice 2 (bundled)").run()
    assert not at.exception and not at.error
    heads = [h.value for h in at.subheader]
    assert "Best tyre to start on" in heads and "Driving styles and head to head" in heads
