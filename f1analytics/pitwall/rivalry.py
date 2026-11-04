import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "styles"
RESULTS_FILE = DATA_DIR / "rivalry_results.json"
OVERTAKES_FILE = DATA_DIR / "overtaking.json"
RESULT_YEARS = (2023, 2024, 2025, 2026)
OVERTAKE_YEARS = (2024, 2025, 2026)
SESSIONS = ("Race", "Sprint", "Qualifying")
MIN_PLACED = 30
PLACE_NAMES = {"Miami Gardens": "Miami", "Monte Carlo": "Monaco", "Yas Island": "Abu Dhabi", "Yas Marina": "Abu Dhabi", "Sakhir": "Bahrain",
               "Lusail": "Qatar", "Marina Bay": "Singapore", "Spa-Francorchamps": "Spa", "Spielberg": "Austria", "Mexico City": "Mexico",
               "Montréal": "Montréal", "São Paulo": "São Paulo", "Austin": "Austin"}
FAMOUS = [("HAM", "VER"), ("HAM", "LEC"), ("HAM", "RUS"), ("VER", "NOR"), ("VER", "LEC"), ("NOR", "PIA"), ("RUS", "ANT"),
          ("LEC", "NOR"), ("LEC", "SAI"), ("VER", "PER")]


def place(name):
    return PLACE_NAMES.get(str(name), str(name))


def _finished_sessions(src, year, names):
    from f1analytics.sources.openf1_source import _ts

    now = pd.Timestamp.utcnow().tz_localize(None)
    s = src._get("sessions", year=int(year))
    if s.empty:
        return s
    s = s[s["session_name"].isin(names) & (_ts(s["date_end"]) < now)]
    if "is_cancelled" in s:
        s = s[~s["is_cancelled"].astype(str).str.lower().isin(["true", "1"])]
    return s.sort_values("date_start")


def build_results(years=RESULT_YEARS, src=None, log=print):
    from f1analytics.sources.openf1_source import OpenF1Source

    src = src or OpenF1Source(timeout=30, retries=5)
    rows = []
    for y in years:
        for _, se in _finished_sessions(src, y, SESSIONS).iterrows():
            sk = int(se["session_key"])
            res, d = src._get("session_result", session_key=sk), src._get("drivers", session_key=sk)
            if res.empty:
                continue
            code = dict(zip(d["driver_number"].astype(int), d["name_acronym"])) if not d.empty else {}
            team = dict(zip(d["driver_number"].astype(int), d["team_name"])) if not d.empty else {}
            for _, x in res.iterrows():
                n = int(x["driver_number"])
                flag = {k: bool(x.get(k)) if pd.notna(x.get(k)) else False for k in ("dnf", "dns", "dsq")}
                pos = pd.to_numeric(pd.Series([x.get("position")]), errors="coerce").iat[0]
                if pd.isna(pos) and pd.notna(x.get("position")) and se["session_name"] != "Qualifying":
                    flag["dnf"] = True
                rows.append({"y": int(y), "loc": place(se.get("location")), "d": str(se["date_start"])[:10], "s": se["session_name"], "k": sk,
                             "c": code.get(n, str(n)), "t": team.get(n), "p": None if pd.isna(pos) else int(pos), **flag})
        log(f"results {y}: {len(rows)} rows")
    return rows


def _corner_fracs(src, sk, laps, ck, year):
    import requests

    from f1analytics.sources.openf1_source import _ts

    clean = laps[laps["clean"]]
    if clean.empty or not ck:
        return None
    n = clean["driver_number"].value_counts().idxmax()
    lap = clean[clean["driver_number"] == n].sort_values("lap_number")
    lap = lap.iloc[len(lap) // 2]
    loc = src._get("location", session_key=sk, driver_number=int(n), **{"date>": lap["start"].isoformat(), "date<": lap["end"].isoformat()})
    if loc.empty:
        return None
    loc = loc.assign(t=_ts(loc["date"])).sort_values("t")
    loc = loc[(loc["x"] != 0) | (loc["y"] != 0)]
    xy = loc[["x", "y"]].to_numpy(float)
    if len(xy) < 20:
        return None
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    ft = ((loc["t"] - lap["start"]).dt.total_seconds() / lap["dur"]).to_numpy()
    fs = seg / seg[-1]
    corners = None
    for yy in (year, year - 1, year - 2):
        try:
            r = requests.get(f"https://api.multiviewer.app/api/v1/circuits/{int(ck)}/{yy}", headers={"User-Agent": "f1-pitwall"}, timeout=15)
            if r.ok and r.json().get("corners"):
                corners = [(c["number"], c["trackPosition"]["x"], c["trackPosition"]["y"]) for c in r.json()["corners"] if c.get("trackPosition")]
                break
        except Exception:
            continue
    if not corners:
        return None
    cf = [(int(c), float(fs[np.argmin(np.hypot(xy[:, 0] - cx, xy[:, 1] - cy))])) for c, cx, cy in corners]
    return {"time": ft.tolist(), "dist": fs.tolist(), "corners": cf}


def nearest_corner(frac, corners):
    if frac is None or not corners:
        return None
    return min(corners, key=lambda c: abs(((frac - c[1]) + 0.5) % 1 - 0.5))[0]


def same_lap_passes(passes, laps):
    by = {int(n): g.sort_values("start") for n, g in laps.groupby("driver_number")}

    def lap_at(n, t):
        g = by.get(int(n))
        if g is None:
            return None
        cur = g[g["start"] <= t]
        return int(cur.iloc[-1]["lap_number"]) if len(cur) else None

    keep = [lap_at(r["by"], r["t"]) is not None and lap_at(r["by"], r["t"]) == lap_at(r["on"], r["t"]) for _, r in passes.iterrows()]
    return passes[np.array(keep, dtype=bool)] if len(passes) else passes


def build_overtakes(years=OVERTAKE_YEARS, src=None, log=print):
    from f1analytics.pitwall import racecraft as rc
    from f1analytics.pitwall.tracks import circuit_key_for
    from f1analytics.sources.openf1_source import OpenF1Source

    src = src or OpenF1Source(timeout=30, retries=5)
    races, passes = [], []
    for y in years:
        for _, se in _finished_sessions(src, y, ("Race",)).iterrows():
            sk = int(se["session_key"])
            raw = {ep: src._get(ep, session_key=sk) for ep in ("drivers", "laps", "pit", "race_control", "overtakes")}
            if raw["laps"].empty or raw["overtakes"] is None or raw["overtakes"].empty:
                continue
            laps = rc._laps(raw)
            found = same_lap_passes(rc._on_track_passes(raw, laps), laps)
            ck = se.get("circuit_key") if pd.notna(se.get("circuit_key")) else circuit_key_for(se.get("circuit_short_name"), se.get("location"))
            name = place(se.get("location"))
            try:
                prof = _corner_fracs(src, sk, laps, ck, int(y))
            except Exception:
                prof = None
            green = int((~laps.groupby("lap_number")["neutral"].any()).sum())
            races.append({"y": int(y), "loc": name, "k": sk, "ck": None if ck is None else int(ck), "laps": int(laps["lap_number"].max()),
                          "green": green, "passes": int(len(found))})
            lap_rows = {n: g.sort_values("start") for n, g in laps.groupby("driver_number")}
            for _, p in found.iterrows():
                frac = corner = None
                g = lap_rows.get(int(p["by"]))
                if g is not None and prof:
                    cur = g[(g["start"] <= p["t"]) & (g["end"] > p["t"])]
                    if len(cur) and pd.notna(cur.iloc[0]["dur"]):
                        c = cur.iloc[0]
                        frac = float(np.interp((p["t"] - c["start"]).total_seconds() / c["dur"], prof["time"], prof["dist"]))
                        corner = nearest_corner(frac, prof["corners"])
                passes.append({"y": int(y), "loc": name, "k": sk, "by": int(p["by"]), "on": int(p["on"]), "corner": corner})
            log(f"{y} {name}: {len(found)} passes")
    return races, passes


def save(results=None, races=None, passes=None, out_dir=DATA_DIR):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if results is not None:
        (out / RESULTS_FILE.name).write_text(json.dumps({"years": sorted({r["y"] for r in results}), "rows": results}, separators=(",", ":")))
    if races is not None:
        (out / OVERTAKES_FILE.name).write_text(json.dumps({"races": races, "passes": passes}, separators=(",", ":")))


def load_results(path=RESULTS_FILE):
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    df = pd.DataFrame(json.loads(p.read_text())["rows"])
    return df[~df["dns"]] if not df.empty else df


def load_overtakes(path=OVERTAKES_FILE):
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(), pd.DataFrame()
    d = json.loads(p.read_text())
    return pd.DataFrame(d["races"]), pd.DataFrame(d["passes"])


def drivers(df, years=None):
    x = df if not years else df[df["y"].isin(years)]
    return sorted(x["c"].dropna().unique())


def head_to_head(df, a, b, session="Race", years=None):
    x = df[(df["s"] == session) & df["c"].isin([a, b])]
    if years:
        x = x[x["y"].isin(years)]
    if x.empty:
        return None
    rows = x.drop_duplicates(["k", "c"]).set_index(["k", "c"])
    keys = [k for k in x["k"].unique() if (k, a) in rows.index and (k, b) in rows.index]
    out = {"n": 0, "a": 0, "b": 0, "both_fin": 0, "a_fin": 0, "b_fin": 0, "podiums": 0, "gaps": [], "races": []}
    for k in keys:
        ra, rb = rows.loc[(k, a)], rows.loc[(k, b)]

        def score(r):
            if session == "Qualifying":
                return r["p"] if pd.notna(r["p"]) else 99
            return 99 if r["dnf"] or r["dsq"] or pd.isna(r["p"]) else r["p"]

        pa, pb = score(ra), score(rb)
        if pa == 99 and pb == 99:
            continue
        out["n"] += 1
        out["a"] += pa < pb
        out["b"] += pb < pa
        if pa < 99 and pb < 99:
            out["both_fin"] += 1
            out["a_fin"] += pa < pb
            out["b_fin"] += pb < pa
            out["gaps"].append(pb - pa)
            out["podiums"] += pa <= 3 and pb <= 3
        out["races"].append({"year": int(ra["y"]), "place": ra["loc"], "date": ra["d"], "a": None if pa == 99 else int(pa), "b": None if pb == 99 else int(pb)})
    out["avg_gap"] = float(np.mean(out["gaps"])) if out["gaps"] else None
    del out["gaps"]
    return out


def by_season(df, a, b, years=None):
    rows = []
    for y in sorted(df["y"].unique()):
        if years and y not in years:
            continue
        r, q, s = (head_to_head(df, a, b, sess, [y]) for sess in ("Race", "Qualifying", "Sprint"))
        if not r or not r["n"]:
            continue
        ta = df[(df["y"] == y) & (df["c"] == a)]["t"].mode()
        tb = df[(df["y"] == y) & (df["c"] == b)]["t"].mode()
        mates = len(ta) and len(tb) and ta.iat[0] == tb.iat[0]
        rows.append({"year": int(y), "race": (r["a"], r["b"]), "qual": (q["a"], q["b"]) if q else (0, 0), "sprint": (s["a"], s["b"]) if s and s["n"] else None,
                     "podiums": r["podiums"], "teammates": bool(mates), "team_a": ta.iat[0] if len(ta) else None, "team_b": tb.iat[0] if len(tb) else None})
    return rows


def season_record(df, code, years=None):
    x = df[(df["c"] == code) & (df["s"] == "Race")]
    if years:
        x = x[x["y"].isin(years)]
    fin = ~(x["dnf"] | x["dsq"]) & x["p"].notna()
    return {"starts": int(len(x)), "wins": int((fin & (x["p"] == 1)).sum()), "podiums": int((fin & (x["p"] <= 3)).sum()),
            "dnfs": int(x["dnf"].sum())}


def famous_table(df, years=None):
    present = set(drivers(df, years))
    out = []
    for a, b in FAMOUS:
        if a not in present or b not in present:
            continue
        r, q = head_to_head(df, a, b, "Race", years), head_to_head(df, a, b, "Qualifying", years)
        if r and r["n"]:
            out.append({"a": a, "b": b, "race": (r["a"], r["b"]), "qual": (q["a"], q["b"]) if q else (0, 0), "podiums": r["podiums"], "avg_gap": r["avg_gap"]})
    return out


def track_table(races, passes, years=None):
    if races.empty:
        return pd.DataFrame()
    r = races[races["passes"] > 0].copy()
    if years:
        r = r[r["y"].isin(years)]
    if r.empty:
        return pd.DataFrame()
    r["per10"] = r["passes"] / r["green"].clip(lower=1) * 10
    g = r.groupby("loc").agg(races=("k", "count"), per10=("per10", "median"), median=("passes", "median"))
    for y in sorted(r["y"].unique()):
        g[str(y)] = r[r["y"] == y].groupby("loc")["passes"].sum()
    spots = []
    for loc in g.index:
        c = corners(passes, loc, years)
        placed = located_share(passes, loc, years)[0] if not passes.empty else 0
        spots.append("too few passes to place" if c and placed < MIN_PLACED else (", ".join(f"T{n} {s:.0%}" for n, s in c[:3]) if c else ""))
    g["spots"] = spots
    return g.sort_values("per10", ascending=False)


def corners(passes, loc, years=None):
    if passes.empty:
        return []
    x = passes[(passes["loc"] == loc) & passes["corner"].notna()]
    if years:
        x = x[x["y"].isin(years)]
    if x.empty:
        return []
    n = x["corner"].astype(int).value_counts()
    return [(int(c), float(v / n.sum())) for c, v in n.items()]


def located_share(passes, loc, years=None):
    x = passes[passes["loc"] == loc]
    if years:
        x = x[x["y"].isin(years)]
    return (int(x["corner"].notna().sum()), int(len(x)))


def year_change(races, a=2025, b=2026):
    r = races[races["passes"] > 0]
    pa, pb = r[r["y"] == a].groupby("loc")["passes"].sum(), r[r["y"] == b].groupby("loc")["passes"].sum()
    both = sorted(set(pa.index) & set(pb.index))
    if not both:
        return None
    up = sum(pb[l] > pa[l] for l in both)
    return {"tracks": len(both), "before": int(pa[both].sum()), "after": int(pb[both].sum()), "up": int(up),
            "biggest": sorted(((l, int(pa[l]), int(pb[l])) for l in both), key=lambda x: x[2] - x[1], reverse=True)[:4]}


YOUNG = [("LIN", "2026's only rookie"), ("ANT", "Second season"), ("HAD", "Second season"), ("BEA", "Second season"),
         ("BOR", "Second season"), ("COL", "Second full season")]


def teammate(df, code, year):
    x = df[(df["y"] == year) & (df["s"] == "Race")]
    mine = x[x["c"] == code]
    if mine.empty:
        return None, None
    team = mine["t"].mode().iat[0]
    mates = x[(x["t"] == team) & (x["c"] != code)]["c"].value_counts()
    return (mates.index[0] if len(mates) else None), team


def young_drivers(df, year, who=YOUNG):
    out = []
    for code, label in who:
        mate, team = teammate(df, code, year)
        if not team:
            continue
        rec = season_record(df, code, [year])
        x = df[(df["y"] == year) & (df["c"] == code) & (df["s"] == "Race")]
        fin = x[~(x["dnf"] | x["dsq"]) & x["p"].notna()]
        r = head_to_head(df, code, mate, "Race", [year]) if mate else None
        q = head_to_head(df, code, mate, "Qualifying", [year]) if mate else None
        out.append({"code": code, "label": label, "team": team, "mate": mate, "starts": rec["starts"], "wins": rec["wins"], "podiums": rec["podiums"],
                    "best": int(fin["p"].min()) if len(fin) else None, "top10": int((fin["p"] <= 10).sum()), "dnfs": rec["dnfs"],
                    "race": (r["a"], r["b"]) if r else None, "qual": (q["a"], q["b"]) if q else None})
    return out
