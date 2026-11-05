import json
from pathlib import Path

import numpy as np
import pandas as pd

from f1analytics.pitwall import racecraft as rc
from f1analytics.pitwall.tracks import circuit_key_for

OLD_RESULTS_FILE = Path(__file__).resolve().parent.parent / "styles" / "race_results_2016_2022.json"
OLD_YEARS = (2016, 2017, 2018, 2019, 2020, 2021, 2022)
TRACK_HALF_LIFE_YEARS = 3.0

METRICS = {
    "pace_pct": ("Race pace", "% off best", -1),
    "brake_later_m": ("Brakes later", "m", 1),
    "corner_speed_kmh": ("Corner speed", "km/h", 1),
    "top_speed_kmh": ("Top speed", "km/h", 1),
    "late_straight_acc": ("Late-straight push", "km/h per s", 1),
    "clip_kmh": ("Clipping", "km/h lost", -1),
    "wear_rel": ("Tyre wear", "s per lap", -1),
}
LAST_N = 5
HALF_LIFE_RACES = 3.0
WEIGHTS = {"low": (0.6, 0.3, 0.1), "base": (0.5, 0.3, 0.2), "high": (0.4, 0.25, 0.35)}
STINT_LAPS = 25
DNF_PLACE = 18


def season_rows(data):
    if not data or not data.get("rows"):
        return pd.DataFrame()
    rows = pd.DataFrame(data["rows"])
    order = {r["session_key"]: i for i, r in enumerate(data.get("races") or [])}
    where = {r["session_key"]: r.get("location") for r in data.get("races") or []}
    rows["i"] = rows["session_key"].map(order)
    rows["location"] = rows["session_key"].map(where)
    return rows.dropna(subset=["i"])


def last_race(data):
    races = (data or {}).get("races") or []
    return races[-1].get("location") if races else None


def driver_table(rows, last=LAST_N):
    if rows.empty:
        return pd.DataFrame()
    n = rows["i"].max()
    cols = [c for c in METRICS if c in rows]
    season = rows.groupby("code")[cols].median()
    recent = rows[rows["i"] > n - last].groupby("code")[cols].median().add_suffix("_last")
    w = 0.5 ** ((n - rows["i"]) / HALF_LIFE_RACES)
    pace_w = rows.assign(w=w).dropna(subset=["pace_pct"]).groupby("code").apply(
        lambda d: float(np.average(d["pace_pct"], weights=d["w"])), include_groups=False).rename("pace_weighted")
    races = rows.groupby("code").size().rename("races")
    return season.join(recent, how="left").join(pace_w).join(races)


def form(results, year, half_life=HALF_LIFE_RACES):
    if results is None or results.empty:
        return pd.Series(dtype=float)
    r = results[(results["y"] == year) & (results["s"] == "Race")].copy()
    if r.empty:
        return pd.Series(dtype=float)
    order = {k: i for i, k in enumerate(r.sort_values("d")["k"].unique())}
    r["i"] = r["k"].map(order)
    n = r["i"].max()
    r["w"] = 0.5 ** ((n - r["i"]) / half_life)
    r["place"] = np.where(r["dnf"] | r["dsq"] | r["p"].isna(), DNF_PLACE, r["p"].fillna(DNF_PLACE))
    return r.groupby("c").apply(lambda d: float(np.average(d["place"], weights=d["w"])), include_groups=False)


def _z(s):
    s = pd.Series(s, dtype=float)
    sd = s.std()
    return (s - s.mean()) / sd if sd and np.isfinite(sd) else s * 0


def ranking(table, form_s, history, min_races=rc.MIN_RACES, field=10.0):
    if table.empty:
        return pd.DataFrame()
    t = table[table["races"] >= min_races].copy()
    t["form"] = form_s.reindex(t.index)
    t = t.dropna(subset=["pace_weighted", "form"])
    if t.empty:
        return t
    recs = {c: (history or {}).get(c) for c in t.index}
    t["track_place"] = [recs[c]["weighted_place"] if recs[c] else field for c in t.index]
    zp, zf, zt = -_z(t["pace_weighted"]), -_z(t["form"]), -_z(t["track_place"])
    for name, (a, b, c) in WEIGHTS.items():
        t[f"score_{name}"] = a * zp + b * zf + c * zt
        t[f"rank_{name}"] = t[f"score_{name}"].rank(ascending=False, method="min").astype(int)
    t["track"] = [recs[c] for c in t.index]
    return t.sort_values("score_base", ascending=False)


def stint_cost(wear, laps=STINT_LAPS):
    if wear is None or pd.isna(wear):
        return None
    return float(wear * laps * (laps - 1) / 2)


def _val(row, key):
    v = row.get(key) if row is not None else None
    return None if v is None or pd.isna(v) else float(v)


def insights(code, table, ranked, lap_s=90.0):
    if code not in table.index:
        return []
    row = table.loc[code]
    out = []
    pace = _val(row, "pace_pct_last")
    if pace is not None:
        recent = table["pace_pct_last"].dropna().sort_values()
        pos = int((recent < pace).sum()) + 1
        out.append(f"Race pace over the last {LAST_N} races: {pace:.2f}% off the best car, about {pace / 100 * lap_s:.2f} s a lap. {pos} of {len(recent)} on the grid.")
    brake, brake_s = _val(row, "brake_later_m_last"), _val(row, "brake_later_m")
    if brake is not None:
        trend = f" (season {brake_s:+.1f} m)" if brake_s is not None else ""
        out.append(f"Brakes {abs(brake):.1f} m {'later' if brake >= 0 else 'earlier'} than the field into the big stops lately{trend}.")
    corner = _val(row, "corner_speed_kmh_last")
    if corner is not None and abs(corner) >= 1:
        out.append(f"Carries {abs(corner):.1f} km/h {'more' if corner > 0 else 'less'} than the field through the slowest point of corners.")
    push = _val(row, "late_straight_acc_last")
    if push is not None:
        if push <= -0.5:
            out.append(f"Runs short of battery late on straights ({push:+.2f} km/h per second against the field): harder to attack and easier to pass on long straights.")
        elif push >= 0.3:
            out.append(f"Still pulling hard at the end of straights ({push:+.2f} km/h per second against the field): strong on long runs to a braking zone.")
    clip = _val(row, "clip_kmh_last")
    if clip is not None and clip >= 1:
        out.append(f"Clipping: loses {clip:.1f} km/h more than the field before braking, a sign the battery runs dry.")
    wear = _val(row, "wear_rel_last")
    if wear is not None:
        cost = stint_cost(wear)
        if abs(cost) < 0.5:
            out.append(f"Tyre wear lately is level with the field: under half a second either way over a {STINT_LAPS}-lap stint.")
        else:
            side = "gains" if cost < 0 else "loses"
            out.append(f"Tyre wear lately {wear:+.3f} s per lap against the field: he {side} about {abs(cost):.1f} s over a {STINT_LAPS}-lap stint.")
    if ranked is not None and code in ranked.index:
        rec = ranked.loc[code, "track"]
        if rec and rec.get("finishes"):
            fins = ", ".join(f"{y}: {'DNF' if f is None else f'P{f}'}" for y, f in zip(rec["years"], rec["finishes"]))
            wins = f" {rec['wins']} win{'s' if rec['wins'] != 1 else ''} here." if rec.get("wins") else ""
            out.append(f"Here before ({fins}).{wins}")
    return out


def build_old_results(years=OLD_YEARS, get=None, log=print):
    import requests

    get = get or (lambda url: requests.get(url, headers={"User-Agent": "f1-pitwall"}, timeout=30).json())
    rows = []
    for y in years:
        offset, total = 0, 1
        while offset < total:
            d = get(f"https://api.jolpi.ca/ergast/f1/{y}/results.json?limit=100&offset={offset}")["MRData"]
            total = int(d["total"])
            for race in d["RaceTable"]["Races"]:
                c = race["Circuit"]
                ck = circuit_key_for(c.get("circuitId"), c["Location"].get("locality"), c.get("circuitName"), c["Location"].get("country"))
                for x in race["Results"]:
                    pt = x["positionText"]
                    rows.append({"y": int(y), "ck": ck, "place": c["Location"].get("locality"), "c": x["Driver"].get("code"),
                                 "grid": int(x["grid"]) if str(x.get("grid", "")).isdigit() else None, "p": int(pt) if pt.isdigit() else None})
            offset += int(d["limit"])
        log(f"{y}: {len(rows)} rows")
    OLD_RESULTS_FILE.write_text(json.dumps({"years": list(years), "rows": rows}, separators=(",", ":")))
    return rows


def load_old_results(path=OLD_RESULTS_FILE):
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=["y", "ck", "c", "p"])
    return pd.DataFrame(json.loads(p.read_text())["rows"])


def track_results(new_results, old_results, location):
    ck = circuit_key_for(location)
    if ck is None:
        return pd.DataFrame(columns=["y", "c", "p"])
    parts = []
    if old_results is not None and not old_results.empty:
        parts.append(old_results[old_results["ck"] == ck][["y", "c", "p"]])
    if new_results is not None and not new_results.empty:
        r = new_results[new_results["s"] == "Race"].copy()
        r["ck"] = [circuit_key_for(l) for l in r["loc"]]
        r = r[r["ck"] == ck]
        r["p"] = np.where(r["dnf"] | r["dsq"], None, r["p"])
        parts.append(r[["y", "c", "p"]])
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["y", "c", "p"])


def track_history(new_results, old_results, location, field=10.0, prior=1.0, half_life=TRACK_HALF_LIFE_YEARS):
    t = track_results(new_results, old_results, location)
    if t.empty:
        return {}
    ref = int(t["y"].max())
    out = {}
    for code, g in t.groupby("c"):
        g = g.sort_values("y")
        w = 0.5 ** ((ref - g["y"]) / half_life)
        place = g["p"].apply(lambda v: 15 if v is None or pd.isna(v) else v).astype(float)
        out[code] = {"finishes": [None if v is None or pd.isna(v) else int(v) for v in g["p"]], "years": [int(y) for y in g["y"]],
                     "wins": int((g["p"] == 1).sum()), "best": None if g["p"].dropna().empty else int(g["p"].dropna().min()),
                     "weighted_place": float((np.sum(place * w) + prior * field) / (w.sum() + prior))}
    return out


LAP_S = {"interlagos": 72.0, "são paulo": 72.0, "sao paulo": 72.0, "las vegas": 95.0, "lusail": 84.0, "qatar": 84.0,
         "yas marina": 87.0, "abu dhabi": 87.0, "mexico": 80.0, "austin": 97.0, "singapore": 94.0, "monaco": 74.0}


def lap_seconds(location, default=90.0):
    key = str(location or "").lower()
    return next((v for k, v in LAP_S.items() if k in key), default)


def build(location, year=2026):
    from f1analytics.pitwall import racecraft, rivalry

    data = racecraft.load(year)
    rows = season_rows(data)
    table = driver_table(rows)
    if table.empty:
        return None
    results = rivalry.load_results()
    history = track_history(results, load_old_results(), location)
    ranked = ranking(table, form(results, year), history)
    teams = rows.sort_values("i").groupby("code")["team"].last() if "team" in rows else pd.Series(dtype=str)
    races = (data or {}).get("races") or []
    return {"table": table, "ranked": ranked, "history": history, "teams": teams.to_dict(), "lap_s": lap_seconds(location),
            "races": len(races), "last": races[-1].get("location") if races else None, "location": location}


def tyre_board(table, n=3):
    w = table["wear_rel_last"].dropna().sort_values() if "wear_rel_last" in table else pd.Series(dtype=float)
    return [(c, float(v), stint_cost(v)) for c, v in w.head(n).items()], [(c, float(v), stint_cost(v)) for c, v in w.tail(n)[::-1].items()]
