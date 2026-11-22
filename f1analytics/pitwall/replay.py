"""Build a compact whole-race replay (every car's map position every DT seconds) for the 3D race replay."""
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from f1analytics.pitwall import georef

DT = 2.0
ORDER_DT = 10.0
DIR = Path(__file__).resolve().parent.parent / "styles" / "replays"


def _ts(s):
    return pd.to_datetime(s, utc=True, format="ISO8601")


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def path_for(session_key):
    return DIR / f"{int(session_key)}.json.gz"


def load(session_key):
    p = path_for(session_key)
    if not p.exists():
        return None
    return json.loads(gzip.decompress(p.read_bytes()))


def flag_states(rc, t0):
    out = []
    if rc is None or len(rc) == 0:
        return out
    rc = rc.assign(t=_ts(rc["date"])).sort_values("t")
    for _, r in rc.iterrows():
        m = str(r.get("message") or "").upper()
        cat = str(r.get("category") or "")
        flag = str(r.get("flag") or "").upper()
        scope = str(r.get("scope") or "").lower()
        state = None
        if cat == "SafetyCar" and "VIRTUAL" in m and "DEPLOYED" in m:
            state = "VSC"
        elif cat == "SafetyCar" and "DEPLOYED" in m:
            state = "SC"
        elif cat == "Flag" and flag == "RED" and scope in ("track", ""):
            state = "RED"
        elif cat == "Flag" and flag == "CHEQUERED":
            state = "FINISH"
        elif (cat == "Flag" and flag == "GREEN" and scope == "track") or "SAFETY CAR IN THIS LAP" in m or "VSC ENDING" in m:
            state = "GREEN"
        if state:
            out.append({"t": round((r["t"] - t0).total_seconds(), 1), "s": state})
    return out


def build(src, session_key):
    sk = int(session_key)
    sess = src._get("sessions", session_key=sk)
    location = str(sess["location"].iloc[0]) if len(sess) else ""
    drivers = src._get("drivers", session_key=sk)
    laps = src._get("laps", session_key=sk)
    laps = laps.assign(t=_ts(laps["date_start"]), dur=_num(laps["lap_duration"]))
    first = laps[laps["lap_number"] == 1]["t"].min()
    t0 = (first if pd.notna(first) else laps["t"].min()) - pd.Timedelta(seconds=20)
    t1 = (laps["t"] + pd.to_timedelta(laps["dur"].fillna(0), unit="s")).max() + pd.Timedelta(seconds=30)
    grid = np.arange(0, (t1 - t0).total_seconds(), DT)
    meta, xy = [], {}
    for _, d in drivers.drop_duplicates("driver_number").iterrows():
        n = int(d["driver_number"])
        loc = src._get("location", session_key=sk, driver_number=n, **{"date>": t0.isoformat(), "date<": t1.isoformat()})
        if loc is None or loc.empty:
            continue
        s = (_ts(loc["date"]) - t0).dt.total_seconds().to_numpy(float)
        o = np.argsort(s)
        s, x, y = s[o], _num(loc["x"]).to_numpy(float)[o], _num(loc["y"]).to_numpy(float)[o]
        ok = np.isfinite(x) & np.isfinite(y) & ~((x == 0) & (y == 0))
        if ok.sum() < 50:
            continue
        s, x, y = s[ok], x[ok], y[ok]
        gx, gy = np.interp(grid, s, x), np.interp(grid, s, y)
        stale = np.interp(grid, s, s)
        gap = np.abs(grid - stale) > 6
        gx[(grid < s[0]) | (grid > s[-1]) | gap] = np.nan
        gy[np.isnan(gx)] = np.nan
        xy[n] = (gx, gy)
        meta.append({"n": n, "code": str(d.get("name_acronym") or n), "team": str(d.get("team_name") or ""),
                     "colour": "#" + str(d.get("team_colour") or "9A9AA8").lstrip("#")})
    clean = laps.dropna(subset=["dur"])
    clean = clean[clean["lap_number"] > 1]
    best = clean.sort_values("dur").iloc[0] if len(clean) else None
    tf = None
    outline_xy = None
    if best is not None and int(best["driver_number"]) in xy:
        loc = src._get("location", session_key=sk, driver_number=int(best["driver_number"]),
                       **{"date>": best["t"].isoformat(), "date<": (best["t"] + pd.Timedelta(seconds=float(best["dur"]))).isoformat()})
        outline_xy = np.column_stack([_num(loc["x"]).to_numpy(float), _num(loc["y"]).to_numpy(float)])
        outline_xy = outline_xy[np.isfinite(outline_xy).all(1) & (np.abs(outline_xy).sum(1) > 0)]
        tf = georef.fit(outline_xy, location)
    if tf is None:
        raise RuntimeError(f"No real-world outline to place {location} on the map")
    cars = []
    for m in meta:
        gx, gy = xy[m["n"]]
        ll = georef.apply(tf, np.column_stack([np.nan_to_num(gx), np.nan_to_num(gy)]))
        lon = [None if np.isnan(a) else round(float(b), 6) for a, b in zip(gx, ll[:, 0])]
        lat = [None if np.isnan(a) else round(float(b), 6) for a, b in zip(gx, ll[:, 1])]
        cars.append({**m, "lon": lon, "lat": lat})
    track = georef.apply(tf, georef.resample(outline_xy, 600))
    pos = src._get("position", session_key=sk)
    order = []
    if pos is not None and len(pos):
        pos = pos.assign(t=(_ts(pos["date"]) - t0).dt.total_seconds()).sort_values("t")
        current = {}
        k = 0
        rows = pos[["t", "driver_number", "position"]].to_numpy()
        for tt in np.arange(0, grid[-1] + ORDER_DT, ORDER_DT):
            while k < len(rows) and rows[k][0] <= tt:
                current[int(rows[k][1])] = int(rows[k][2])
                k += 1
            order.append([n for n, _ in sorted(current.items(), key=lambda kv: kv[1])])
    lap_starts = laps.groupby("lap_number")["t"].min().sort_index()
    lap_t = [round((t - t0).total_seconds(), 1) for t in lap_starts]
    rc = src._get("race_control", session_key=sk)
    return {"session_key": sk, "location": location, "t0": t0.isoformat(), "dt": DT, "order_dt": ORDER_DT,
            "track": [[round(float(a), 6), round(float(b), 6)] for a, b in track], "fit_rms_m": round(tf["rms_m"], 1),
            "cars": cars, "order": order, "lap_t": lap_t, "flags": flag_states(rc, t0)}


def save(data):
    DIR.mkdir(parents=True, exist_ok=True)
    p = path_for(data["session_key"])
    p.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode()))
    return p
