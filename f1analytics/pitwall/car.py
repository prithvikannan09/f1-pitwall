import numpy as np
import pandas as pd

from f1analytics.analysis.degradation import fit_stint

LONG_RUN_MIN_LAPS = 5
LONG_RUN_BAND = 0.03
DRAG_BAND_KMH = 3.0
TOW_JUMP_KMH = 8.0
HARVEST_DROP_KMH = 8.0
TOW_GAP_S = 1.2


def laps_table(snapshot):
    rows = snapshot.get("laps") or []
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in ("lap_time", "st", "i1", "i2", "fl", "tyre_age", "stint"):
        if col not in df:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["track_status"] = df["track_status"].fillna("1").astype(str)
    df["clean"] = df["lap_time"].notna() & ~df["pit_in"].fillna(False).astype(bool) & ~df["pit_out"].fillna(False).astype(bool) & (df["track_status"] == "1")
    team = {d["number"]: d.get("team") for d in snapshot.get("drivers", [])}
    df["team"] = df["number"].astype(str).map(team)
    return df


def speed_profile(snapshot, focus_code, teammate_code=None):
    df = laps_table(snapshot)
    if df.empty or df["st"].notna().sum() < 10:
        return None
    clean = df[df["clean"] & df["st"].notna()]
    per = clean.groupby("code")["st"].median()
    if focus_code not in per.index:
        return None
    field = float(per.median())
    mine = float(per[focus_code])
    delta = mine - field
    rank = int((per > mine).sum()) + 1
    level = "less wing than most (lower drag)" if delta > DRAG_BAND_KMH else ("more wing than most (higher downforce)" if delta < -DRAG_BAND_KMH else "about the same wing as the field")
    out = {
        "top_speed": mine, "field_median": field, "delta": delta, "rank": rank, "cars": int(len(per)), "level": level,
        "teammate": None, "by_team": clean.groupby("team")["st"].median().sort_values(ascending=False).round(1).to_dict(),
    }
    if teammate_code and teammate_code in per.index:
        out["teammate"] = {"code": teammate_code, "delta": mine - float(per[teammate_code])}
    for key in ("i1", "i2"):
        sub = df[df["clean"] & df[key].notna()].groupby("code")[key].median()
        if focus_code in sub.index and len(sub) > 3:
            out[f"{key}_delta"] = float(sub[focus_code] - sub.median())
    return out


def mode_hints(snapshot, focus_code, last_n=12):
    df = laps_table(snapshot)
    if df.empty:
        return []
    mine = df[(df["code"] == focus_code) & df["st"].notna()].sort_values("lap")
    clean = mine[mine["clean"]]
    if len(clean) < 5:
        return []
    base = float(clean["st"].median())
    pace = float(clean["lap_time"].median())
    hints = []
    for r in mine.tail(last_n).itertuples():
        jump = r.st - base
        note = None
        if r.pit_in or r.pit_out:
            continue
        if r.track_status != "1":
            note = "Neutralised lap (Safety Car / VSC / yellow): slow speeds expected."
        elif jump >= TOW_JUMP_KMH:
            note = "Big top-speed gain: likely a tow from a car ahead and/or extra battery power (Boost or Overtake mode)."
        elif jump <= -HARVEST_DROP_KMH:
            slow = r.lap_time is not None and not np.isnan(r.lap_time) and r.lap_time > pace * 1.02
            note = "Top speed well down" + (" and a slow lap: likely saving energy, lifting or managing tyres." if slow else ": likely recharging the battery on the straight.")
        if note:
            hints.append({"lap": int(r.lap), "speed_trap": float(r.st), "vs_normal": float(jump), "note": note})
    return hints


def long_runs(snapshot, focus_team=None):
    df = laps_table(snapshot)
    if df.empty:
        return pd.DataFrame()
    runs = []
    for (code, stint), g in df[df["clean"]].groupby(["code", "stint"]):
        g = g.sort_values("lap")
        med = g["lap_time"].median()
        band = g[(g["lap_time"] - med).abs() <= LONG_RUN_BAND * med]
        if len(band) < LONG_RUN_MIN_LAPS:
            continue
        slope = None
        if band["tyre_age"].nunique() >= 4:
            slope = float(fit_stint(band["tyre_age"].astype(float), band["lap_time"].astype(float))["beta"])
        runs.append({
            "driver": code, "team": g["team"].iloc[0], "stint": int(stint), "compound": g["compound"].iloc[-1],
            "laps": int(len(band)), "avg": float(band["lap_time"].mean()), "best": float(band["lap_time"].min()),
            "wear": slope, "start_age": int(band["tyre_age"].min()) if band["tyre_age"].notna().any() else None,
        })
    return pd.DataFrame(runs)


def practice_summary(snapshot, team, focus_code):
    drivers = [d for d in snapshot.get("drivers", []) if d.get("position")]
    fastest = min([d["best_lap"] for d in drivers if d.get("best_lap")] or [None]) if drivers else None
    runs = long_runs(snapshot)
    cars = []
    for d in sorted([d for d in drivers if team.lower() in str(d.get("team") or "").lower()], key=lambda d: (d["code"] != focus_code, d["position"])):
        mine = runs[runs["driver"] == d["code"]] if len(runs) else runs
        compare = []
        for r in (mine.itertuples() if len(mine) else []):
            same = runs[(runs["compound"] == r.compound)]
            best_other = same[same["driver"] != d["code"]].sort_values("avg").head(1)
            compare.append({
                "compound": r.compound, "laps": r.laps, "avg": r.avg, "wear": r.wear,
                "rank": int((same["avg"] < r.avg).sum()) + 1, "of": int(len(same)),
                "vs_best": (r.avg - float(best_other["avg"].iloc[0])) if len(best_other) else None,
                "best_driver": best_other["driver"].iloc[0] if len(best_other) else None,
            })
        cars.append({"car": d, "gap_to_fastest": (d["best_lap"] - fastest) if (d.get("best_lap") and fastest) else None, "runs": compare})
    wear = pd.DataFrame()
    if len(runs) and runs["wear"].notna().any():
        wear = runs.dropna(subset=["wear"]).groupby("compound").agg(runs=("wear", "size"), wear_s_per_lap=("wear", "median"), avg_pace=("avg", "median")).reset_index()
    return {"cars": cars, "runs": runs, "wear": wear, "fastest": fastest}
