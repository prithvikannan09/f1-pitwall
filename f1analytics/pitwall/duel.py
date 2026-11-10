import numpy as np
import pandas as pd

GRID_N = 800
MIN_SAMPLES = 60


def _ts(s):
    return pd.to_datetime(s, utc=True, errors="coerce", format="mixed").dt.tz_convert(None)


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def lap_window(lap_row, pad=0.0):
    t0 = pd.Timestamp(lap_row["date_start"])
    t0 = t0.tz_convert(None) if t0.tzinfo else t0
    return t0 - pd.Timedelta(seconds=pad), t0 + pd.Timedelta(seconds=float(lap_row["lap_duration"]) + pad)


def stale_runs(v, min_run=3, jump=40.0):
    v = np.asarray(v, dtype=float)
    flag = np.zeros(len(v), dtype=bool)
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[j + 1] == v[i]:
            j += 1
        if j - i + 1 >= min_run and v[i] > 120 and j + 1 < len(v) and abs(v[j + 1] - v[j]) >= jump:
            flag[i:j + 2] = True
        i = j + 1
    return flag


def trace(car, loc, t0, t1, lap_time=None, sectors=None):
    if car is None or len(car) == 0:
        return None
    c = car.assign(t=_ts(car["date"]))
    c = c[(c["t"] >= t0) & (c["t"] <= t1)].sort_values("t").drop_duplicates("t")
    if len(c) < MIN_SAMPLES:
        return None
    sec = (c["t"] - pd.Timestamp(t0)).dt.total_seconds().to_numpy(dtype=float)
    v = _num(c["speed"]).ffill().bfill().to_numpy(dtype=float)
    dist = np.concatenate([[0.0], np.cumsum((v[1:] + v[:-1]) / 2 / 3.6 * np.diff(sec))])
    out = pd.DataFrame({
        "s": sec, "d": dist, "v": v,
        "thr": _num(c["throttle"]).clip(0, 100).to_numpy(dtype=float),
        "brk": (_num(c["brake"]).fillna(0) > 0).to_numpy(),
        "gear": _num(c["n_gear"]).to_numpy(dtype=float),
    })
    out["gap"] = stale_runs(v)
    out.attrs["lap_time"] = float(lap_time) if lap_time else float(sec[-1])
    out.attrs["sectors"] = [float(x) for x in sectors] if sectors is not None and all(pd.notna(x) for x in sectors) else None
    if loc is not None and len(loc):
        p = loc.assign(t=_ts(loc["date"]))
        p = p[(p["t"] >= t0 - pd.Timedelta(seconds=1)) & (p["t"] <= t1 + pd.Timedelta(seconds=1))].sort_values("t")
        if len(p) >= 10:
            ps = (p["t"] - pd.Timestamp(t0)).dt.total_seconds().to_numpy(dtype=float)
            out["x"] = np.interp(sec, ps, _num(p["x"]).to_numpy(dtype=float))
            out["y"] = np.interp(sec, ps, _num(p["y"]).to_numpy(dtype=float))
    out["f"] = out["d"] / out["d"].iloc[-1]
    return out


def project(ref, t, window=80):
    if "x" not in ref or "x" not in t:
        return t
    rd = np.linspace(0, ref["d"].iloc[-1], 3000)
    rx, ry = np.interp(rd, ref["d"], ref["x"]), np.interp(rd, ref["d"], ref["y"])
    xs, ys = t["x"].to_numpy(), t["y"].to_numpy()
    out, i = [], 0
    for k, (x, y) in enumerate(zip(xs, ys)):
        lo = 0 if k == 0 else max(0, i - 5)
        hi = min(len(rd), (window if k == 0 else i + window))
        j = lo + int(np.argmin((rx[lo:hi] - x) ** 2 + (ry[lo:hi] - y) ** 2))
        i = max(i, j)
        out.append(rd[i])
    t = t.copy()
    t.attrs = dict(getattr(t, "attrs", {}))
    d = np.maximum.accumulate(np.asarray(out, dtype=float))
    d[-1] = max(d[-1], rd[-1] * 0.995)
    t["f"] = d / rd[-1]
    return t


def compare(a, b, n=GRID_N):
    a, b = project(a, a), project(a, b)
    f = np.linspace(0, 1, n)
    length = float((a["d"].iloc[-1] + b["d"].iloc[-1]) / 2)
    res = pd.DataFrame({"f": f, "m": f * length})
    for tag, t in (("a", a), ("b", b)):
        ff, ss = t["f"].to_numpy(dtype=float), t["s"].to_numpy(dtype=float)
        keep = (ss <= t.attrs.get("lap_time", ss[-1])) & (ff > 1e-9) & (ff < 1 - 1e-9)
        ff, ss = np.concatenate([[0.0], ff[keep], [1.0]]), np.concatenate([[0.0], ss[keep], [t.attrs.get("lap_time", ss[-1])]])
        ff = np.maximum.accumulate(ff)
        ff, idx = np.unique(ff, return_index=True)
        res[f"t_{tag}"] = np.interp(f, ff, ss[idx])
        res[f"v_{tag}"] = np.interp(f, t["f"], t["v"])
        res[f"thr_{tag}"] = np.interp(f, t["f"], t["thr"])
        res[f"brk_{tag}"] = np.interp(f, t["f"], t["brk"].astype(float)) > 0.5
        g = np.interp(f, t["f"], t["gap"].astype(float)) > 0.01 if "gap" in t else np.zeros(n, dtype=bool)
        k = max(1, int(0.025 * n))
        res[f"gap_{tag}"] = np.convolve(g.astype(int), np.ones(2 * k + 1, dtype=int), mode="same") > 0
    res["delta"] = res["t_b"] - res["t_a"]
    res = anchor_sectors(res, a.attrs.get("sectors"), b.attrs.get("sectors"))
    src = a if "x" in a else (b if "x" in b else None)
    if src is not None:
        res["x"] = np.interp(f, src["f"], src["x"])
        res["y"] = np.interp(f, src["f"], src["y"])
    return res


def anchor_sectors(res, sa, sb):
    if not sa or not sb or len(sa) != 3 or len(sb) != 3 or any(pd.isna(v) for v in list(sa) + list(sb)):
        return res
    ca, cb = np.cumsum(sa), np.cumsum(sb)
    fa = [float(np.interp(ca[i], res["t_a"], res["f"])) for i in range(2)]
    if not (0 < fa[0] < fa[1] < 1):
        return res
    xs = [0.0, fa[0], fa[1], 1.0]
    want = [0.0, cb[0] - ca[0], cb[1] - ca[1], cb[2] - ca[2]]
    have = list(np.interp(xs, res["f"], res["delta"]))
    res = res.copy()
    res["delta"] = res["delta"] + np.interp(res["f"], xs, np.subtract(want, have))
    res.attrs["sector_f"] = fa
    return res


def corner_fractions(cmp, corners):
    if "x" not in cmp or not corners:
        return []
    xs, ys = cmp["x"].to_numpy(), cmp["y"].to_numpy()
    out = []
    for c in corners:
        if isinstance(c, dict):
            p = c.get("trackPosition") or {}
            if "x" not in p:
                continue
            num, cx, cy = c.get("number"), p["x"], p["y"]
        else:
            num, cx, cy = c
        i = int(np.argmin((xs - cx) ** 2 + (ys - cy) ** 2))
        out.append((int(num or 0), float(cmp["f"].iloc[i])))
    out.sort(key=lambda t: t[1])
    return out


def segments(cmp, corners=None, k=12):
    cf = corner_fractions(cmp, corners or [])
    if len(cf) >= 4:
        mids = [0.0] + [(cf[i][1] + cf[i + 1][1]) / 2 for i in range(len(cf) - 1)] + [1.0]
        labels = [f"Turn {n}" for n, _ in cf]
        bounds = list(zip(mids[:-1], mids[1:]))
        merged_l, merged_b = [], []
        for lab, (lo, hi) in zip(labels, bounds):
            if merged_b and hi - lo < 0.012:
                plo, _ = merged_b[-1]
                merged_b[-1] = (plo, hi)
                merged_l[-1] = merged_l[-1] + "–" + lab.split()[-1]
            else:
                merged_l.append(lab)
                merged_b.append((lo, hi))
        return list(zip(merged_l, merged_b))
    edges = np.linspace(0, 1, k + 1)
    return [(f"Part {i + 1} of the lap", (edges[i], edges[i + 1])) for i in range(k)]


def _first_brake(seg, tag):
    b = seg[seg[f"brk_{tag}"]]
    return float(b["m"].iloc[0]) if len(b) else None


def segment_table(cmp, corners=None):
    rows = []
    for label, (lo, hi) in segments(cmp, corners):
        seg = cmp[(cmp["f"] >= lo) & (cmp["f"] <= hi)]
        if len(seg) < 3:
            continue
        dl, dh = np.interp([lo, hi], cmp["f"], cmp["delta"])
        gain_b = float(-(dh - dl))
        ba, bb = _first_brake(seg, "a"), _first_brake(seg, "b")
        rows.append({
            "where": label, "f0": lo, "f1": hi, "gain_b": gain_b,
            "min_a": float(seg["v_a"].min()), "min_b": float(seg["v_b"].min()),
            "max_a": float(seg["v_a"].max()), "max_b": float(seg["v_b"].max()),
            "brake_a": ba, "brake_b": bb,
            "thr_a": float(seg["thr_a"].mean()), "thr_b": float(seg["thr_b"].mean()),
            "gap_a": bool(seg["gap_a"].any()), "gap_b": bool(seg["gap_b"].any()),
        })
    return pd.DataFrame(rows)


def explain(row, a_code, b_code):
    winner, loser = (b_code, a_code) if row["gain_b"] > 0 else (a_code, b_code)
    w, l = ("b", "a") if row["gain_b"] > 0 else ("a", "b")
    bits = []
    dmin = row[f"min_{w}"] - row[f"min_{l}"]
    dmax = row[f"max_{w}"] - row[f"max_{l}"]
    bw, bl = row[f"brake_{w}"], row[f"brake_{l}"]
    if bw is not None and bl is not None and bw - bl >= 5:
        bits.append(f"braked about {bw - bl:.0f} m later")
    if dmin >= 2:
        bits.append(f"carried {dmin:.0f} km/h more through the slowest point")
    if dmax >= 3:
        bits.append(f"was {dmax:.0f} km/h faster at the top end")
    dthr = row[f"thr_{w}"] - row[f"thr_{l}"]
    if not bits and dthr >= 3:
        bits.append(f"was on the throttle more ({dthr:.0f}% more on average)")
    if not bits:
        bits.append("was a little quicker all the way through")
    note = ""
    gaps = [c for c, k in ((a_code, "gap_a"), (b_code, "gap_b")) if row.get(k)]
    if gaps:
        note = f" ({' and '.join(gaps)}'s telemetry has a short gap here, so treat this one with care.)"
        bits = [] if dmin < 2 and dmax < 3 else bits
    text = f"{winner} gained {abs(row['gain_b']):.3f}s at {row['where']}"
    return text + (f": {', and '.join(bits)}." if bits else ".") + note


def gap_breakdown(laps, a, b):
    x = laps[laps["driver_number"].isin([a, b])].dropna(subset=["t", "lap_duration"]).copy()
    if x.empty:
        return None
    x["end"] = x["t"] + pd.to_timedelta(x["lap_duration"], unit="s")
    ea = x[x["driver_number"] == a].set_index("lap_number")
    eb = x[x["driver_number"] == b].set_index("lap_number")
    common = sorted(set(ea.index) & set(eb.index))
    if len(common) < 3:
        return None
    gap = pd.Series({n: (eb.at[n, "end"] - ea.at[n, "end"]).total_seconds() for n in common})
    first = common[0]
    start_gap = (eb.at[first, "t"] - ea.at[first, "t"]).total_seconds() if first > 1 else 0.0
    rows = []
    prev = start_gap
    for n in common:
        change = gap[n] - prev
        prev = gap[n]
        ra, rb = ea.loc[n], eb.loc[n]
        if n == 1:
            kind = "Start and lap 1"
        elif bool(ra.get("pit_in")) or bool(ra.get("pit_out")) or bool(rb.get("pit_in")) or bool(rb.get("pit_out")):
            kind = "Pit stops"
        elif bool(ra.get("neutral")) or bool(rb.get("neutral")):
            kind = "Safety car and VSC laps"
        else:
            kind = "Racing laps"
        rows.append({"lap": n, "gap": float(gap[n]), "change": float(change), "kind": kind})
    df = pd.DataFrame(rows)
    racing = df[df["kind"] == "Racing laps"]
    buckets = df.groupby("kind")["change"].agg(["sum", "count"]).reindex(
        ["Start and lap 1", "Racing laps", "Pit stops", "Safety car and VSC laps"]).dropna(how="all").fillna(0)
    return {"laps": df, "buckets": buckets, "final_gap": float(df["gap"].iloc[-1]), "start_gap": start_gap,
            "racing_per_lap": float(racing["change"].mean()) if len(racing) else None, "last_lap": int(common[-1])}


def stint_pace(laps, a, b):
    from f1analytics.pitwall import review as rv

    rows = []
    for lo, hi in rv.green_windows(laps):
        w = laps[laps["clean"] & laps["lap_number"].between(lo, hi)]
        pa = w[w["driver_number"] == a]["lap_duration"]
        pb = w[w["driver_number"] == b]["lap_duration"]
        if len(pa) >= 3 and len(pb) >= 3:
            ca = w[w["driver_number"] == a]["compound"].mode()
            cb = w[w["driver_number"] == b]["compound"].mode()
            rows.append({"laps": f"{lo}–{hi}", "a": float(pa.median()), "b": float(pb.median()),
                         "diff": float(pb.median() - pa.median()), "n": int(min(len(pa), len(pb))),
                         "tyre_a": ca.iloc[0] if len(ca) else None, "tyre_b": cb.iloc[0] if len(cb) else None})
    return pd.DataFrame(rows)


COMPOUND_COLOUR = {"SOFT": "#E10600", "MEDIUM": "#FFD12E", "HARD": "#F0F0F0", "INTERMEDIATE": "#43B02A", "WET": "#0067FF"}
COMPOUND_SHORT = {"SOFT": "S", "MEDIUM": "M", "HARD": "H", "INTERMEDIATE": "I", "WET": "W"}


def stints_for(raw, num):
    st = raw.get("stints")
    if st is None or len(st) == 0:
        return []
    x = st[st["driver_number"] == num].sort_values("stint_number")
    out = []
    for _, r in x.iterrows():
        if pd.isna(r.get("lap_start")):
            continue
        out.append({"n": int(r["stint_number"]), "compound": str(r.get("compound") or "UNKNOWN").upper(),
                    "start": int(r["lap_start"]), "end": int(r["lap_end"]) if pd.notna(r.get("lap_end")) else None,
                    "age0": int(r["tyre_age_at_start"]) if pd.notna(r.get("tyre_age_at_start")) else 0})
    return out


def fuel_per_lap(total_laps):
    from f1analytics import config

    return config.FUEL_SEC_PER_KG * config.START_FUEL_KG / max(int(total_laps or 0), 1)


def stint_wear(laps, num, stint, total_laps, min_laps=4):
    end = stint["end"] or int(laps["lap_number"].max())
    base = laps[(laps["driver_number"] == num) & laps["lap_number"].between(stint["start"] + 1, end)].dropna(subset=["lap_duration"])
    x = base[base["clean"]]
    if len(x) < min_laps:
        keep = ~base.get("pit_in", False).astype(bool) & ~base.get("pit_out", False).astype(bool) & ~base.get("neutral", False).astype(bool)
        x = base[keep]
    if len(x) < min_laps:
        return {"laps": end - stint["start"] + 1, "clean": len(x), "pace": float(x["lap_duration"].median()) if len(x) else None, "wear": None}
    med = x["lap_duration"].median()
    x = x[(x["lap_duration"] - med).abs() < 2.5]
    slope = float(np.polyfit(x["lap_number"].astype(float), x["lap_duration"].astype(float), 1)[0]) if len(x) >= min_laps else None
    return {"laps": end - stint["start"] + 1, "clean": len(x), "pace": float(x["lap_duration"].median()),
            "wear": None if slope is None else slope + fuel_per_lap(total_laps)}


def stint_of(stints, lap):
    for s in stints:
        if s["start"] <= lap <= (s["end"] if s["end"] is not None else 10 ** 6):
            return s
    return None


def wear_on_lap(laps, raw, num, lap, total_laps):
    stint = stint_of(stints_for(raw, num), int(lap))
    if stint is None:
        return None
    w = stint_wear(laps, num, stint, total_laps)
    end = stint["end"] or int(laps["lap_number"].max())
    x = laps[(laps["driver_number"] == num) & laps["lap_number"].between(stint["start"], end)].dropna(subset=["lap_duration"])
    keep = pd.Series(True, index=x.index)
    for c in ("pit_in", "pit_out", "neutral"):
        if c in x:
            keep &= ~x[c].astype(bool)
    keep |= x["lap_number"] == int(lap)
    x = x[keep]
    into = int(lap) - stint["start"]
    fpl = fuel_per_lap(total_laps)
    pts = pd.DataFrame({"lap": x["lap_number"].astype(int), "age": stint["age0"] + x["lap_number"].astype(int) - stint["start"],
                        "time": x["lap_duration"].astype(float) + fpl * (x["lap_number"].astype(int) - stint["start"])})
    if w["pace"] is not None:
        pts = pts[((pts["time"] - w["pace"]).abs() < 6) | (pts["lap"] == int(lap))]
    return {"compound": stint["compound"], "age": stint["age0"] + into, "into": into, "start": stint["start"], "end": end,
            "wear": w["wear"], "cost": None if w["wear"] is None else w["wear"] * into, "points": pts.reset_index(drop=True)}


def speed_traps(raw_laps, num):
    if raw_laps is None or len(raw_laps) == 0:
        return pd.DataFrame()
    cols = [c for c in ("st_speed", "i1_speed", "i2_speed") if c in raw_laps]
    x = raw_laps[raw_laps["driver_number"] == num][["lap_number"] + cols].copy()
    for c in cols:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    return x.sort_values("lap_number")
