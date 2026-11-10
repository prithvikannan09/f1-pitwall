import numpy as np
import pandas as pd

from f1analytics.pitwall import duel, review

WET = {"INTERMEDIATE", "WET"}


def skippable_stops(raw, num):
    sts = duel.stints_for(raw, num)
    out = []
    for old, new in zip(sts, sts[1:]):
        if old["end"] is None or new["end"] is None:
            continue
        if (old["compound"] in WET) != (new["compound"] in WET):
            continue
        out.append({"lap": old["end"], "old": old, "new": new})
    return out


def _times(laps, num):
    x = laps[laps["driver_number"] == num].dropna(subset=["lap_duration"])
    return x.set_index("lap_number")["lap_duration"].astype(float), set(x.loc[x["clean"], "lap_number"])


def pit_cost(laps, num, in_lap):
    t, clean = _times(laps, num)
    if in_lap not in t.index or in_lap + 1 not in t.index:
        return None
    pre = [t[n] for n in range(in_lap - 4, in_lap) if n in clean]
    post = [t[n] for n in range(in_lap + 2, in_lap + 6) if n in clean]
    if len(pre) < 2 or len(post) < 2:
        return None
    return float(t[in_lap] - np.median(pre) + t[in_lap + 1] - np.median(post))


def stay_out_refs(raw, laps, num, stop, min_before=3, min_after=5):
    lap, old, new = stop["lap"], stop["old"], stop["new"]
    mine, mclean = _times(laps, num)
    out = []
    for r in sorted(set(laps["driver_number"]) - {num}):
        st = next((s for s in duel.stints_for(raw, int(r)) if s["compound"] == old["compound"] and s["start"] <= lap - 4
                   and (s["end"] or 0) >= lap + 6), None)
        if st is None:
            continue
        theirs, tclean = _times(laps, r)
        both = mclean & tclean
        before = [mine[n] - theirs[n] for n in range(max(lap - 8, old["start"] + 1, st["start"] + 1), lap) if n in both]
        after = [mine[n] - theirs[n] for n in range(lap + 2, min(new["end"], st["end"])) if n in both]
        if len(before) < min_before or len(after) < min_after:
            continue
        out.append({"driver": int(r), "gain": float(np.median(before) - np.median(after)), "until": int(st["end"]),
                    "age_end": int(st["age0"] + st["end"] - st["start"])})
    return out


def tyre_gain(raw, laps, num, stop, total_laps):
    refs = stay_out_refs(raw, laps, num, stop)
    if refs:
        g = np.array([max(r["gain"], 0.0) for r in refs])
        return {"method": "stayed_out", "low": float(np.quantile(g, 0.25)), "base": float(np.median(g)), "high": float(np.quantile(g, 0.75)), "refs": refs}
    w = duel.stint_wear(laps, num, stop["new"], total_laps)["wear"]
    if w is None or w <= 0:
        return None
    gap = stop["old"]["age0"] + stop["lap"] + 1 - stop["old"]["start"] - stop["new"]["age0"]
    base = w * gap
    return {"method": "wear_model", "low": 0.5 * base, "base": base, "high": 1.5 * base, "refs": [], "wear": w, "age_gap": gap}


def skip_stop(raw, laps, num, stop):
    total = int(laps["lap_number"].max())
    cost = pit_cost(laps, num, stop["lap"])
    gain = tyre_gain(raw, laps, num, stop, total)
    if cost is None or gain is None:
        return None
    n = stop["new"]["end"] - stop["lap"]
    net = {k: cost - gain[g] * n for k, g in (("low", "high"), ("base", "base"), ("high", "low"))}
    old = stop["old"]
    longest = 0
    for r in set(laps["driver_number"]):
        for s in duel.stints_for(raw, int(r)):
            if s["compound"] == old["compound"] and s["end"]:
                longest = max(longest, s["age0"] + s["end"] - s["start"] + 1)
    return {"lap": stop["lap"], "compound": old["compound"], "cost": cost, "gain": gain, "laps": n, "net": net,
            "age_needed": old["age0"] + stop["new"]["end"] - old["start"] + 1, "longest_seen": longest}


def reclassify(laps, num, saved):
    ends = review.race_time(laps)
    mine = ends[ends.index.get_level_values(0) == num]
    if mine.empty:
        return None
    n = int(mine.index.get_level_values(1).max())
    me = mine.loc[(num, n)]
    at = ends.xs(n, level="lap_number")
    new = me - pd.Timedelta(seconds=saved)
    if saved >= 0:
        moved = at[(at < me) & (at > new)]
    else:
        moved = at[(at > me) & (at < new)]
    ahead = at[at < me].sort_values(ascending=False)
    return {"lap": n, "places": int(len(moved)) * (1 if saved >= 0 else -1),
            "passed": [(int(d), abs(float((t - new).total_seconds()))) for d, t in moved.sort_values(ascending=saved < 0).items() if d != num],
            "ahead": [(int(d), float((me - t).total_seconds())) for d, t in ahead.items()][:6]}


def all_stops(raw, num):
    sts = duel.stints_for(raw, num)
    return [{"lap": old["end"], "old": old, "new": new} for old, new in zip(sts, sts[1:]) if old["end"] is not None]


def other_laps(raw, laps, num, stop, reach=3):
    out = {}
    for r in sorted(set(laps["driver_number"]) - {num}):
        for s in all_stops(raw, int(r)):
            if s["new"]["compound"] == stop["new"]["compound"] and s["lap"] != stop["lap"] and abs(s["lap"] - stop["lap"]) <= reach:
                out.setdefault(s["lap"], []).append(int(r))
    return dict(sorted(out.items()))


def _offset(mine, theirs, mclean, tclean, lo, hi):
    both = mclean & tclean
    parts = []
    for rng in (range(lo - 6, lo), range(hi + 1, hi + 7)):
        d = [mine[n] - theirs[n] for n in rng if n in both]
        if len(d) >= 2:
            parts.append(float(np.median(d)))
    return float(np.mean(parts)) if parts else None


def move_stop(raw, laps, num, stop, new_lap):
    refs = other_laps(raw, laps, num, stop).get(new_lap) or []
    lo, hi = min(new_lap, stop["lap"]), max(new_lap, stop["lap"]) + 1
    mine, mclean = _times(laps, num)
    window = list(range(lo, hi + 1))
    if any(n not in mine.index for n in window):
        return None
    actual = float(sum(mine[n] for n in window))
    rows = []
    for r in refs:
        theirs, tclean = _times(laps, r)
        if any(n not in theirs.index for n in window):
            continue
        off = _offset(mine, theirs, mclean, tclean, lo, hi)
        if off is None:
            continue
        rows.append({"driver": r, "offset": off, "saved": actual - float(sum(theirs[n] for n in window)) - off * len(window)})
    if not rows:
        return None
    s = np.array([x["saved"] for x in rows])
    return {"from": stop["lap"], "to": new_lap, "window": (lo, hi), "actual": actual, "refs": rows,
            "net": {"low": float(np.quantile(s, 0.25)), "base": float(np.median(s)), "high": float(np.quantile(s, 0.75))}}
