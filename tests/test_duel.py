import numpy as np
import pandas as pd

from f1analytics.pitwall import duel


def _lap(speed_scale, n=300, lap_time=80.0, start="2026-11-08T18:00:00", radius=700.0):
    t = pd.date_range(start, periods=n, freq=pd.Timedelta(seconds=lap_time / n))
    phase = np.linspace(0, 2 * np.pi, n, endpoint=False)
    base = 200 + 80 * np.sin(3 * phase)
    v = base * speed_scale
    car = pd.DataFrame({"date": t.astype(str), "speed": v.round(), "throttle": 90, "brake": (np.cos(3 * phase) > 0.9).astype(int), "n_gear": 7})
    loc = pd.DataFrame({"date": t.astype(str), "x": radius * np.cos(phase), "y": radius * np.sin(phase)})
    return car, loc


def _trace(scale, lap_time):
    car, loc = _lap(scale, lap_time=lap_time)
    t0 = pd.Timestamp("2026-11-08T18:00:00")
    return duel.trace(car, loc, t0, t0 + pd.Timedelta(seconds=lap_time), lap_time, None)


def test_corner_gains_add_up_to_lap_difference():
    a, b = _trace(1.0, 80.0), _trace(1.01, 79.4)
    cmp = duel.compare(a, b)
    assert abs(cmp["delta"].iloc[0]) < 1e-6
    assert abs(cmp["delta"].iloc[-1] - (79.4 - 80.0)) < 1e-6
    seg = duel.segment_table(cmp)
    assert abs(seg["gain_b"].sum() - 0.6) < 1e-3
    assert (seg["gain_b"] > 0).sum() >= len(seg) - 2


def test_sector_anchoring_matches_official_sectors():
    a, b = _trace(1.0, 80.0), _trace(1.0, 80.0)
    a.attrs["sectors"] = [26.0, 27.0, 27.0]
    b.attrs["sectors"] = [26.2, 27.0, 26.8]
    cmp = duel.compare(a, b)
    f1 = cmp.attrs["sector_f"][0]
    assert abs(np.interp(f1, cmp["f"], cmp["delta"]) - 0.2) < 1e-3
    assert abs(cmp["delta"].iloc[-1]) < 1e-6


def test_stale_speed_runs_are_flagged():
    v = [200, 205, 212, 212, 212, 212, 122, 110, 100]
    flag = duel.stale_runs(v)
    assert flag[2:7].all() and not flag[0]


def test_explain_mentions_braking_and_corner_speed():
    row = {"where": "Turn 1", "gain_b": 0.12, "min_a": 100.0, "min_b": 106.0, "max_a": 310.0, "max_b": 311.0,
           "brake_a": 120.0, "brake_b": 135.0, "thr_a": 60.0, "thr_b": 61.0, "gap_a": False, "gap_b": False}
    text = duel.explain(row, "HAM", "VER")
    assert text.startswith("VER gained 0.120s at Turn 1") and "15 m later" in text and "6 km/h more" in text


def test_gap_breakdown_buckets_sum_to_final_gap():
    rows = []
    t0 = pd.Timestamp("2026-11-08T17:00:00")
    for num, lap_t in ((44, 80.0), (3, 79.5)):
        t = t0
        for lap in range(1, 11):
            dur = lap_t + (20 if lap == 5 else 0)
            rows.append({"driver_number": num, "lap_number": lap, "t": t, "lap_duration": dur,
                         "pit_in": lap == 5, "pit_out": False, "neutral": False, "clean": lap not in (1, 5)})
            t = t + pd.Timedelta(seconds=dur)
    g = duel.gap_breakdown(pd.DataFrame(rows), 44, 3)
    assert abs(g["buckets"]["sum"].sum() - g["final_gap"]) < 1e-6
    assert abs(g["final_gap"] - (-5.0)) < 1e-6


def test_wear_on_lap_finds_stint_and_cost():
    import pandas as pd
    from f1analytics.pitwall import duel
    from f1analytics import config

    total = 20
    fpl = duel.fuel_per_lap(total)
    rows = [{"driver_number": 44, "lap_number": n, "lap_duration": 80.0 + (0.1 - fpl) * (n - 1) if n <= 10 else 78.0 + (0.05 - fpl) * (n - 11),
             "clean": n not in (1, 10, 11), "pit_in": n == 10, "pit_out": n == 11, "neutral": False} for n in range(1, 21)]
    laps = pd.DataFrame(rows)
    raw = {"stints": pd.DataFrame([{"driver_number": 44, "stint_number": 1, "compound": "SOFT", "lap_start": 1, "lap_end": 10, "tyre_age_at_start": 2},
                                   {"driver_number": 44, "stint_number": 2, "compound": "MEDIUM", "lap_start": 11, "lap_end": 20, "tyre_age_at_start": 0}])}
    w = duel.wear_on_lap(laps, raw, 44, 8, total)
    assert w["compound"] == "SOFT" and w["age"] == 9 and w["into"] == 7
    assert abs(w["wear"] - 0.1) < 1e-6 and abs(w["cost"] - 0.7) < 1e-6
    assert 8 in set(w["points"]["lap"]) and 10 not in set(w["points"]["lap"])
    w2 = duel.wear_on_lap(laps, raw, 44, 15, total)
    assert w2["compound"] == "MEDIUM" and abs(w2["wear"] - 0.05) < 1e-6
    assert duel.wear_on_lap(laps, raw, 44, 99, total) is None
