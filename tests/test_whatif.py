import pandas as pd

from f1analytics.pitwall import whatif


def _race():
    t0 = pd.Timestamp("2026-11-08T17:00:00Z")
    rows, stints = [], []
    plan = {44: (80.0, 20), 16: (80.3, None), 63: (79.0, None)}
    for num, (pace, stop) in plan.items():
        t = t0
        for n in range(1, 41):
            dur = pace
            if stop and n == stop:
                dur += 5
            if stop and n == stop + 1:
                dur += 18
            if stop and n > stop + 1:
                dur -= 0.4
            rows.append({"driver_number": num, "lap_number": n, "lap_duration": dur, "t": t, "clean": n > 1 and not (stop and n in (stop, stop + 1)),
                         "pit_in": bool(stop and n == stop), "pit_out": bool(stop and n == stop + 1), "neutral": False})
            t += pd.Timedelta(seconds=dur)
        if stop:
            stints += [{"driver_number": num, "stint_number": 1, "compound": "SOFT", "lap_start": 1, "lap_end": stop, "tyre_age_at_start": 0},
                       {"driver_number": num, "stint_number": 2, "compound": "SOFT", "lap_start": stop + 1, "lap_end": 40, "tyre_age_at_start": 0}]
        else:
            stints.append({"driver_number": num, "stint_number": 1, "compound": "SOFT", "lap_start": 1, "lap_end": 40, "tyre_age_at_start": 0})
    return {"stints": pd.DataFrame(stints)}, pd.DataFrame(rows)


def test_skip_stop_uses_drivers_who_stayed_out():
    raw, laps = _race()
    stops = whatif.skippable_stops(raw, 44)
    assert [s["lap"] for s in stops] == [20]
    r = whatif.skip_stop(raw, laps, 44, stops[0])
    assert abs(r["cost"] - 23.4) < 1e-6
    assert r["gain"]["method"] == "stayed_out" and abs(r["gain"]["base"] - 0.4) < 1e-6
    assert r["laps"] == 20 and abs(r["net"]["base"] - (23.4 - 0.4 * 20)) < 1e-6
    assert r["age_needed"] == 40 and r["longest_seen"] == 40


def test_reclassify_counts_cars_passed():
    raw, laps = _race()
    base = whatif.reclassify(laps, 44, 0.0)
    assert base["places"] == 0 and [d for d, _ in base["ahead"]] == [16, 63]
    got = whatif.reclassify(laps, 44, 15.0)
    assert got["places"] == 1 and got["passed"][0][0] == 16


def test_wet_to_dry_stop_cannot_be_skipped():
    raw = {"stints": pd.DataFrame([
        {"driver_number": 44, "stint_number": 1, "compound": "INTERMEDIATE", "lap_start": 1, "lap_end": 14, "tyre_age_at_start": 0},
        {"driver_number": 44, "stint_number": 2, "compound": "SOFT", "lap_start": 15, "lap_end": 38, "tyre_age_at_start": 0},
        {"driver_number": 44, "stint_number": 3, "compound": "SOFT", "lap_start": 39, "lap_end": 62, "tyre_age_at_start": 0},
        {"driver_number": 44, "stint_number": 4, "compound": "INTERMEDIATE", "lap_start": 63, "lap_end": 70, "tyre_age_at_start": 0}])}
    assert [s["lap"] for s in whatif.skippable_stops(raw, 44)] == [38]


def test_wet_start_picks_wet_weather_tyres():
    from f1analytics.pitwall.engine import wet_start

    assert wet_start({"drivers": [{"compound": "SOFT"}, {"compound": "MEDIUM"}], "weather": {"Rainfall": 0}}) is None
    assert wet_start({"drivers": [{"compound": "INTERMEDIATE"}] * 18 + [{"compound": "SOFT"}] * 4})["compound"] == "INTERMEDIATE"
    assert wet_start({"drivers": [{"compound": "WET"}] * 20})["compound"] == "WET"
    assert wet_start({"drivers": [], "weather": {"Rainfall": 1}})["compound"] == "INTERMEDIATE"
    assert wet_start({"drivers": []}, {"kind": "rain", "rain_prob": 80})["compound"] == "INTERMEDIATE"
    assert wet_start({"drivers": []}, {"kind": "dry", "rain_prob": 10}) is None


def test_move_stop_copies_a_driver_who_pitted_earlier():
    t0 = pd.Timestamp("2026-11-08T17:00:00Z")
    rows, stints = [], []
    for num, stop, pace in ((44, 21, 80.0), (16, 20, 80.5)):
        t = t0
        for n in range(1, 31):
            dur = pace
            if n == stop:
                dur += 4 + (25 if num == 44 else 0)
            if n == stop + 1:
                dur += 18
            if num == 44 and n == 20:
                dur -= 3
            rows.append({"driver_number": num, "lap_number": n, "lap_duration": dur, "t": t, "clean": n > 1 and n not in (stop, stop + 1) and not (num == 44 and n == 20),
                         "pit_in": n == stop, "pit_out": n == stop + 1, "neutral": False})
            t += pd.Timedelta(seconds=dur)
        stints += [{"driver_number": num, "stint_number": 1, "compound": "SOFT", "lap_start": 1, "lap_end": stop, "tyre_age_at_start": 0},
                   {"driver_number": num, "stint_number": 2, "compound": "INTERMEDIATE", "lap_start": stop + 1, "lap_end": 30, "tyre_age_at_start": 0}]
    raw, laps = {"stints": pd.DataFrame(stints)}, pd.DataFrame(rows)
    stop = whatif.all_stops(raw, 44)[0]
    assert whatif.other_laps(raw, laps, 44, stop) == {20: [16]}
    r = whatif.move_stop(raw, laps, 44, stop, 20)
    assert r["window"] == (20, 22) and abs(r["refs"][0]["offset"] + 0.5) < 1e-6
    assert abs(r["net"]["base"] - 22.0) < 1e-6
