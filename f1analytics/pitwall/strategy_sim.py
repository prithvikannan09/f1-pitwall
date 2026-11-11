import numpy as np
import pandas as pd

from f1analytics.pitwall import duel, whatif

COMPOUNDS = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]
DRY = {"SOFT", "MEDIUM", "HARD"}
WET = {"INTERMEDIATE", "WET"}
CONDS = ["dry", "inter", "wet"]
COND_NAME = {"dry": "Dry", "inter": "Damp (inters)", "wet": "Wet (full wets)"}
BEST = {"dry": "SOFT", "inter": "INTERMEDIATE", "wet": "WET"}
# Estimates used only when nobody ran that tyre in that condition: seconds per lap slower than the right tyre on a new set, and wear per lap.
DEFAULT_PACE = {
    "dry": {"SOFT": 0.0, "MEDIUM": 0.35, "HARD": 0.7, "INTERMEDIATE": 6.0, "WET": 10.0},
    "inter": {"SOFT": 8.0, "MEDIUM": 8.5, "HARD": 9.0, "INTERMEDIATE": 0.0, "WET": 1.5},
    "wet": {"SOFT": 15.0, "MEDIUM": 15.5, "HARD": 16.0, "INTERMEDIATE": 2.5, "WET": 0.0},
}
DEFAULT_WEAR = {
    "dry": {"SOFT": 0.09, "MEDIUM": 0.06, "HARD": 0.04, "INTERMEDIATE": 0.25, "WET": 0.35},
    "inter": {"SOFT": 0.0, "MEDIUM": 0.0, "HARD": 0.0, "INTERMEDIATE": 0.05, "WET": 0.08},
    "wet": {"SOFT": 0.0, "MEDIUM": 0.0, "HARD": 0.0, "INTERMEDIATE": 0.04, "WET": 0.03},
}
MIN_POINTS = 8
MAX_STOPS = 3
MIN_STINT = 3
RAMP = 3


def track_state(raw, laps):
    total = int(laps["lap_number"].max())
    rows = []
    stints = {int(n): duel.stints_for(raw, int(n)) for n in laps["driver_number"].unique()}
    for lap in range(1, total + 1):
        on = [s["compound"] for sts in stints.values() for s in [duel.stint_of(sts, lap)] if s]
        known = [c for c in on if c in DRY or c in WET]
        wet = sum(c in WET for c in known)
        full = sum(c == "WET" for c in known)
        share = wet / len(known) if known else 0.0
        cond = "wet" if known and full * 2 >= len(known) else ("inter" if known and wet * 2 >= len(known) else "dry")
        rows.append({"lap": lap, "cars": len(known), "wet_share": share, "full_wet_share": full / len(known) if known else 0.0, "cond": cond})
    return pd.DataFrame(rows)


def rain_by_lap(weather, laps):
    if weather is None or len(weather) == 0 or "t" not in laps:
        return pd.DataFrame(columns=["lap", "rain", "track", "air"])
    w = weather.copy()
    w["date"] = pd.to_datetime(w["date"], utc=True, format="ISO8601")
    starts = pd.to_datetime(laps.dropna(subset=["t"]).groupby("lap_number")["t"].min().sort_index())
    if starts.dt.tz is None:
        starts = starts.dt.tz_localize("UTC")
    out = []
    for lap, t0 in starts.items():
        t1 = starts.get(lap + 1, t0 + pd.Timedelta(minutes=3))
        x = w[(w["date"] >= t0 - pd.Timedelta(seconds=30)) & (w["date"] < t1 + pd.Timedelta(seconds=30))]
        if x.empty:
            x = w.iloc[[int((w["date"] - t0).abs().argmin())]]
        out.append({"lap": int(lap), "rain": bool(pd.to_numeric(x["rainfall"], errors="coerce").fillna(0).max() > 0),
                    "track": float(pd.to_numeric(x["track_temperature"], errors="coerce").mean()),
                    "air": float(pd.to_numeric(x["air_temperature"], errors="coerce").mean())})
    return pd.DataFrame(out)


def _wear_table(raw, laps, state, total):
    cond = dict(zip(state["lap"], state["cond"]))
    got = {}
    for n in laps["driver_number"].unique():
        for s in duel.stints_for(raw, int(n)):
            end = s["end"] or total
            cs = {cond.get(lap) for lap in range(s["start"] + 1, end + 1)}
            if len(cs) != 1 or end - s["start"] < 6:
                continue
            w = duel.stint_wear(laps, int(n), s, total)["wear"]
            if w is not None:
                got.setdefault((s["compound"], cs.pop()), []).append(w)
    out, src = {}, {}
    for c in COMPOUNDS:
        for k in CONDS:
            v = got.get((c, k), [])
            if len(v) >= 2:
                out[(c, k)], src[(c, k)] = float(np.clip(np.median(v), 0.0, 0.6)), f"measured ({len(v)} stints)"
            else:
                out[(c, k)], src[(c, k)] = DEFAULT_WEAR[k][c], "estimate"
    return out, src


def family(c):
    return "wet" if c in WET else "slick"


MAJOR = {"dry": "slick", "inter": "wet", "wet": "wet"}
ANCHOR = {("slick", "dry"): "SOFT", ("slick", "inter"): "SOFT", ("slick", "wet"): "SOFT",
          ("wet", "dry"): "INTERMEDIATE", ("wet", "inter"): "INTERMEDIATE", ("wet", "wet"): "WET"}
# Estimated gap of the other tyre family's best tyre when nobody ran it on that lap (seconds a lap slower).
FAMILY_GAP = {"dry": 6.0, "dry_rain": 1.0, "inter": 8.0, "wet": 15.0}


def _within(c, k):
    fam = family(c)
    return DEFAULT_PACE[k][c] - DEFAULT_PACE[k][ANCHOR[(fam, k)]]


def fit(raw, laps, rain=None):
    done = laps.dropna(subset=["lap_duration"])
    total = int(done.groupby("driver_number")["lap_number"].max().max())
    laps = laps[laps["lap_number"] <= total]
    state = track_state(raw, laps)
    cond = dict(zip(state["lap"], state["cond"]))
    raining = set(rain.loc[rain["rain"], "lap"]) if rain is not None and len(rain) else set()
    wear, wear_src = _wear_table(raw, laps, state, total)
    x = laps[laps["clean"] & laps["lap_duration"].notna() & laps["compound"].isin(COMPOUNDS)].copy()
    x["cond"] = x["lap_number"].map(cond)
    x["fam"] = x["compound"].map(family)
    x["major"] = x["fam"] == x["cond"].map(MAJOR)
    x["age"] = pd.to_numeric(x["tyre_age"], errors="coerce").fillna(0)
    grp = x.groupby(["lap_number", "compound"])["lap_duration"].transform("median")
    x = x[(x["lap_duration"] - grp).abs() < 3]
    x["w"] = [wear[(c, k)] for c, k in zip(x["compound"], x["cond"])]
    within = {(c, k): _within(c, k) for c in COMPOUNDS for k in CONDS}
    drv = pd.Series(0.0, index=x["driver_number"].unique())
    maj = x[x["major"]]
    for _ in range(8):
        d = np.array([within[(c, k)] for c, k in zip(maj["compound"], maj["cond"])])
        r = maj["lap_duration"] - d - maj["w"] * maj["age"] - maj["driver_number"].map(drv).fillna(0)
        ref = r.groupby(maj["lap_number"]).median()
        e = maj["lap_duration"] - maj["lap_number"].map(ref) - maj["w"] * maj["age"] - maj["driver_number"].map(drv).fillna(0)
        med = e.groupby([maj["compound"], maj["cond"]]).agg(["median", "size"])
        for (c, k), g in e.groupby([maj["compound"], maj["cond"]]):
            ages = maj.loc[g.index, "age"]
            if len(g) >= 4 * MIN_POINTS and ages.std() >= 3:
                slope = float(np.polyfit(ages.astype(float), (g + maj.loc[g.index, "w"] * ages).astype(float), 1)[0])
                wear[(c, k)] = float(np.clip(slope, 0.0, 0.8))
                wear_src[(c, k)] = f"measured (cars on different tyre ages, {len(g)} laps)"
        maj = maj.assign(w=[wear[(c, k)] for c, k in zip(maj["compound"], maj["cond"])])
        for k in CONDS:
            fam = MAJOR[k]
            a = ANCHOR[(fam, k)]
            have = {c: float(med.loc[(c, k), "median"]) for c in COMPOUNDS if family(c) == fam and (c, k) in med.index and med.loc[(c, k), "size"] >= MIN_POINTS}
            base = have.get(a)
            if base is None and have:
                c0 = min(have, key=have.get)
                base = have[c0] - _within(c0, k)
            for c in COMPOUNDS:
                if family(c) == fam:
                    within[(c, k)] = (have[c] - base) if c in have and base is not None else _within(c, k)
        d = np.array([within[(c, k)] for c, k in zip(maj["compound"], maj["cond"])])
        res = maj["lap_duration"] - maj["lap_number"].map(ref) - d - maj["w"] * maj["age"]
        drv = res.groupby(maj["driver_number"]).median()
        drv = drv - drv.median()
    full = pd.Series(np.nan, index=range(1, total + 1))
    full.loc[ref.index] = ref.values
    field = laps.groupby("lap_number")["lap_duration"].median().reindex(full.index)
    filled = full.interpolate(limit_direction="both")
    hole = full.isna()
    filled[hole] = (field - field.shift(-1) + filled.shift(-1))[hole].fillna(filled[hole])
    minor = x[~x["major"]].copy()
    minor["e"] = (minor["lap_duration"] - minor["lap_number"].map(filled) - minor["w"] * minor["age"] - minor["driver_number"].map(drv).fillna(0)
                  - np.array([within[(c, k)] for c, k in zip(minor["compound"], minor["cond"])]))
    got = minor.groupby("lap_number")["e"].median()
    gap, gap_src = {}, {}
    for lap in range(1, total + 1):
        k = cond.get(lap, "dry")
        if lap in got.index:
            gap[lap], gap_src[lap] = float(got[lap]), "measured"
            continue
        key = "dry_rain" if k == "dry" and lap in raining else k
        est = FAMILY_GAP[key]
        near = [(abs(m - lap), m) for m in got.index if abs(m - lap) < RAMP and all(cond.get(i) == k for i in range(min(m, lap), max(m, lap) + 1))]
        if near:
            dist, m = min(near)
            est = float(got[m]) + (est - float(got[m])) * dist / RAMP
        gap[lap], gap_src[lap] = est, "estimate"
    for c in COMPOUNDS:
        for k in CONDS:
            if family(c) != MAJOR[k]:
                within[(c, k)] = _within(c, k)
    counts = x.groupby(["compound", "cond"]).size()
    pace_src = {(c, k): (f"measured ({int(counts[(c, k)])} laps)" if (c, k) in counts.index and counts[(c, k)] >= MIN_POINTS else "estimate")
                for c in COMPOUNDS for k in CONDS}
    return {"total": total, "state": state, "cond": cond, "ref": filled, "delta": within, "gap": gap, "gap_src": gap_src, "wear": wear,
            "pace_src": pace_src, "wear_src": wear_src, "driver": drv, "pit_loss": pit_loss(raw, laps), "raining": sorted(raining)}


def lap_delta(model, c, lap):
    k = model["cond"].get(lap, "dry")
    d = model["delta"][(c, k)]
    if family(c) != MAJOR[k]:
        d += model["gap"].get(lap, FAMILY_GAP[k])
    return d


def pit_loss(raw, laps):
    costs = []
    for n in laps["driver_number"].unique():
        for s in whatif.all_stops(raw, int(n)):
            c = whatif.pit_cost(laps, int(n), s["lap"])
            if c is not None and 10 < c < 45:
                costs.append(c)
    return float(np.median(costs)) if costs else 22.0


def lap_costs(model):
    n = model["total"]
    ref = model["ref"].reindex(range(1, n + 1)).to_numpy()
    base, wear = {}, {}
    for c in COMPOUNDS:
        base[c] = np.array([ref[i] + lap_delta(model, c, i + 1) for i in range(n)])
        wear[c] = np.array([model["wear"][(c, model["cond"].get(i + 1, "dry"))] for i in range(n)])
    return base, wear


def stint_matrix(base, wear, min_len=MIN_STINT):
    n = len(base)
    L = np.arange(1, n + 1, dtype=float)
    B = np.concatenate([[0.0], np.cumsum(base)])
    W0 = np.concatenate([[0.0], np.cumsum(wear)])
    W1 = np.concatenate([[0.0], np.cumsum(wear * L)])
    s = np.arange(1, n + 1)[:, None]
    e = np.arange(1, n + 1)[None, :]
    with np.errstate(invalid="ignore"):
        m = (B[e] - B[s - 1]) + (W1[e] - W1[s - 1]) - s * (W0[e] - W0[s - 1])
    m[e < s + min_len - 1] = np.inf
    return m


def legal(compounds):
    used = set(compounds)
    return bool(used & WET) or len(used & DRY) >= 2


def plan_time(model, plan, mats=None):
    if mats is None:
        base, wear = lap_costs(model)
        mats = {c: stint_matrix(base[c], wear[c], 1) for c in COMPOUNDS}
    n = model["total"]
    edges = [0] + list(plan["pits"]) + [n]
    t = 0.0
    for c, a, b in zip(plan["compounds"], edges[:-1], edges[1:]):
        if b <= a:
            return np.inf
        t += mats[c][a, b - 1]
    return float(t + model["pit_loss"] * len(plan["pits"]))


def optimise(model, start=None, max_stops=MAX_STOPS):
    n = model["total"]
    base, wear = lap_costs(model)
    mats = {c: stint_matrix(base[c], wear[c]) for c in COMPOUNDS}
    bit = {c: 1 << i for i, c in enumerate(COMPOUNDS)}
    pit = model["pit_loss"]
    layers = [{}]
    for c in ([start] if start else COMPOUNDS):
        layers[0][(bit[c], c)] = (mats[c][0, :].copy(), None)
    for k in range(1, max_stops + 1):
        cur = {}
        for (mask, last), (f, _) in layers[k - 1].items():
            prev = np.concatenate([[np.inf], f[:-1]])
            for c in COMPOUNDS:
                cand = prev[:, None] + pit + mats[c]
                best_s = np.argmin(cand, axis=0)
                val = cand[best_s, np.arange(n)]
                key = (mask | bit[c], c)
                old = cur.get(key)
                if old is None:
                    cur[key] = (val, {"s": best_s, "from": np.full(n, -1, dtype=object)})
                    for e in range(n):
                        cur[key][1]["from"][e] = (mask, last)
                else:
                    better = val < old[0]
                    if better.any():
                        old[0][better] = val[better]
                        old[1]["s"][better] = best_s[better]
                        for e in np.where(better)[0]:
                            old[1]["from"][e] = (mask, last)
        layers.append(cur)
    out = []
    for k, layer in enumerate(layers):
        for (mask, last), (f, _) in layer.items():
            comps = [c for c in COMPOUNDS if mask & bit[c]]
            if not legal(comps) or not np.isfinite(f[n - 1]):
                continue
            out.append((float(f[n - 1]), k, (mask, last)))
    if not out:
        return []
    plans = []
    for total, k, key in sorted(out)[:40]:
        compounds, pits, e = [], [], n - 1
        for kk in range(k, -1, -1):
            mask, last = key
            compounds.append(last)
            if kk == 0:
                break
            info = layers[kk][key][1]
            s = int(info["s"][e])
            pits.append(s)
            key = info["from"][e]
            e = s - 1
        plan = {"compounds": compounds[::-1], "pits": pits[::-1], "time": total, "stops": k}
        if plan not in plans:
            plans.append(plan)
    return plans


def best_by_start(model):
    rows = []
    for c in COMPOUNDS:
        p = optimise(model, start=c)
        if p:
            rows.append(p[0])
    rows.sort(key=lambda p: p["time"])
    return rows


def actual_plan(raw, num, total):
    sts = duel.stints_for(raw, num)
    if not sts:
        return None
    return {"compounds": [s["compound"] for s in sts], "pits": [s["end"] for s in sts[:-1] if s["end"]], "stops": len(sts) - 1}


def describe(plan):
    parts = [plan["compounds"][0].title()]
    for c, lap in zip(plan["compounds"][1:], plan["pits"]):
        parts.append(f"{c.title()} from lap {lap + 1}")
    return " → ".join(parts)
