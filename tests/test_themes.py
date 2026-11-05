from f1analytics.ui import themes as t


def test_time_of_day_from_local_time_and_fallback():
    assert t.time_of_day({"now_utc": "2026-11-08T17:00:00", "gmt_offset": "-03:00:00"}) == "day"
    assert t.time_of_day({"now_utc": "2026-12-06T13:30:00+00:00", "gmt_offset": "04:00:00"}) == "dusk"
    assert t.time_of_day({"now_utc": "2026-11-22T06:00:00", "gmt_offset": "-08:00:00"}) == "night"
    assert t.time_of_day({"session": {"circuit": "Marina Bay"}}) == "night"
    assert t.time_of_day({"session": {"circuit": "Interlagos"}}) == "day"


def test_helmet_accent_and_readable_ink():
    ham, lec = t.helmet("HAM"), t.helmet("LEC")
    assert ham["lead"] != lec["lead"]
    assert ham["ink"] == "#15151E" and lec["ink"] == "#FFFFFF"
    assert t.helmet("XYZ", "#123456")["lead"] == "#123456"


def test_page_theme_layers_follow_conditions():
    rain_night, info = t.page_theme("HAM", "Ferrari", "#E80020", "rain", "night")
    assert "class='pwx-drop'" in rain_night and "class='pwx-rigv'" in rain_night and "pwx-field lit" in rain_night
    assert info["helmet"]["lead"] == "#FFCC00" and info["weather"] == "rain" and info["time"] == "night"
    hot_day, _ = t.page_theme("VER", "Red Bull Racing", "#3671C6", "hot", "day")
    assert "class='pwx-heat'" in hot_day and "class='pwx-glare'" in hot_day and "class='pwx-drop'" not in hot_day
    dry_dusk, _ = t.page_theme("NOR", "McLaren", "#FF8000", "dry", "dusk")
    assert "class='pwx-dusk'" in dry_dusk and "class='pwx-sheen'" in dry_dusk and "class='pwx-rigv'" not in dry_dusk
    again, _ = t.page_theme("HAM", "Ferrari", "#E80020", "rain", "night")
    assert again == rain_night


def test_ground_tints_by_team_and_conditions():
    _, a = t.page_theme("HAM", "Ferrari", "#E80020", "dry", "day")
    _, b = t.page_theme("HAM", "Ferrari", "#E80020", "rain", "day")
    _, c = t.page_theme("VER", "Red Bull Racing", "#3671C6", "dry", "day")
    assert len({a["ground"], b["ground"], c["ground"]}) == 3


def test_colour_key_covers_every_condition():
    from f1analytics.ui.pitwall_page import COLOUR_KEY
    keys = {(g, k) for g, k, *_ in COLOUR_KEY}
    for w in ("dry", "hot", "rain"):
        assert ("weather", w) in keys
    for t in ("day", "dusk", "night"):
        assert ("time", t) in keys
