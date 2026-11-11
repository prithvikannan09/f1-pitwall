from pathlib import Path
import unicodedata

import numpy as np
import pandas as pd

MIN_CLEAN = 10
ALIASES = {"kuala lumpur": "sepang", "marina bay": "singapore", "miami gardens": "miami", "monte carlo": "monaco"}
TEAM_KEYS = {"haas f1 team": "Haas", "red bull racing": "Red Bull", "racing bulls": "Racing Bulls", "aston martin": "Aston Martin"}


def _plain(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()


def team_name(t):
    p = _plain(t)
    return TEAM_KEYS.get(p, str(t))


def team_pace(data):
    races = data.get("races") or []
    order = {r["session_key"]: i for i, r in enumerate(races)}
    loc = {r["session_key"]: r["location"] for r in races}
    df = pd.DataFrame(data.get("rows") or [])
    if df.empty:
        return pd.DataFrame(columns=["race", "location", "team", "gap"])
    df = df[(pd.to_numeric(df["clean_laps"], errors="coerce") >= MIN_CLEAN) & df["pace_pct"].notna() & df["session_key"].isin(order)]
    t = df.groupby(["session_key", "team"])["pace_pct"].min().reset_index()
    t["gap"] = t["pace_pct"] - t.groupby("session_key")["pace_pct"].transform("min")
    t["race"] = t["session_key"].map(order)
    t["location"] = t["session_key"].map(loc)
    t["team"] = t["team"].map(team_name)
    return t.sort_values(["race", "gap"])[["race", "location", "team", "gap"]].reset_index(drop=True)


def upgrade_events(extras, races):
    out = []
    for r in extras["upgrades"]["rounds"]:
        lab = _plain(r["label"])
        hit = None
        for i, race in enumerate(races):
            names = [_plain(race["location"])]
            names += [ALIASES[n] for n in names if n in ALIASES]
            if any(n and n in lab for n in names):
                hit = i
        for team, n in r["counts"].items():
            if n:
                out.append({"race": hit, "label": r["label"], "team": team, "parts": int(n), "items": (r.get("items") or {}).get(team) or []})
    return pd.DataFrame(out, columns=["race", "label", "team", "parts", "items"])


def verdicts(pace, events, k=5):
    rows = []
    for team, g in pace.groupby("team"):
        g = g.sort_values("race")
        early, late = g["gap"].head(k).mean(), g["gap"].tail(k).mean()
        parts = int(events.loc[events["team"] == team, "parts"].sum()) if len(events) else 0
        change = late - early
        verdict = "Closed the gap" if change <= -0.2 else ("Fell back" if change >= 0.2 else "No real change")
        rows.append({"team": team, "parts": parts, "early": float(early), "recent": float(late), "change": float(change), "verdict": verdict})
    return pd.DataFrame(rows).sort_values("recent").reset_index(drop=True)


def event_effect(pace, events, team, n=3):
    g = pace[pace["team"] == team].set_index("race")["gap"]
    out = []
    for _, e in events[(events["team"] == team) & events["race"].notna()].sort_values("race").iterrows():
        i = int(e["race"])
        before = g[(g.index < i) & (g.index >= i - n)]
        after = g[(g.index >= i) & (g.index < i + n)]
        out.append({"label": e["label"], "race": i, "parts": e["parts"], "items": e["items"],
                    "before": float(before.mean()) if len(before) else None, "after": float(after.mean()) if len(after) else None,
                    "change": float(after.mean() - before.mean()) if len(before) and len(after) else None})
    return out


def _finish(row):
    return int(row["position"]) if str(row["text"]).isdigit() else 22


def driver_form(results, pace_rows=None):
    if results is None or results.empty:
        return pd.DataFrame()
    rounds = sorted(results["round"].unique())
    half = rounds[(len(rounds) + 1) // 2 - 1]
    r = results.copy()
    r["fin"] = [_finish(x) for _, x in r.iterrows()]
    r["first"] = r["round"] <= half
    pace = {}
    if pace_rows is not None and len(pace_rows):
        p = pace_rows.dropna(subset=["pace_pct"])
        for code, g in p.groupby("code"):
            pace[code] = (g.loc[g["first"], "pace_pct"].median(), g.loc[~g["first"], "pace_pct"].median())
    out = []
    for code, g in r.groupby("code"):
        a, b = g[g["first"]], g[~g["first"]]
        ppr_a = a["points"].sum() / max(len(a), 1)
        ppr_b = b["points"].sum() / max(len(b), 1)
        row = {"code": code, "driver": g["driver"].iloc[-1], "team": g.sort_values("round")["team"].iloc[-1], "points": float(g["points"].sum()),
               "races": int(len(g)), "ppr_first": float(ppr_a), "ppr_second": float(ppr_b), "ppr_change": float(ppr_b - ppr_a),
               "fin_first": float(a["fin"].mean()) if len(a) else np.nan, "fin_second": float(b["fin"].mean()) if len(b) else np.nan,
               "dnf_first": int((~a["text"].astype(str).str.isdigit()).sum()), "dnf_second": int((~b["text"].astype(str).str.isdigit()).sum()),
               "pace_first": pace.get(code, (np.nan, np.nan))[0], "pace_second": pace.get(code, (np.nan, np.nan))[1]}
        ch, fch = row["ppr_change"], row["fin_second"] - row["fin_first"]
        if ch <= -3 or (ch <= -1.5 and fch >= 2):
            row["form"] = "Started strong, faded"
        elif ch >= 3 or (ch >= 1.5 and fch <= -2):
            row["form"] = "Finishing strong"
        else:
            row["form"] = "Steady"
        out.append(row)
    df = pd.DataFrame(out).sort_values("points", ascending=False).reset_index(drop=True)
    df.attrs["half"] = int(half)
    df.attrs["rounds"] = [int(x) for x in rounds]
    return df


def pace_halves(data):
    races = data.get("races") or []
    half_race = (len(races) + 1) // 2
    order = {r["session_key"]: i for i, r in enumerate(races)}
    df = pd.DataFrame(data.get("rows") or [])
    if df.empty:
        return df
    df = df[(pd.to_numeric(df["clean_laps"], errors="coerce") >= MIN_CLEAN) & df["session_key"].isin(order)].copy()
    df["first"] = df["session_key"].map(order) < half_race
    return df


def cumulative_points(results):
    r = results.pivot_table(index="round", columns="code", values="points", aggfunc="sum").fillna(0).sort_index()
    return r.cumsum()


TEL = {"corner_speed_kmh": "Corner speed", "top_speed_kmh": "Top speed", "brake_later_m": "Braking point"}


def team_metrics(data):
    races = data.get("races") or []
    order = {r["session_key"]: i for i, r in enumerate(races)}
    df = pd.DataFrame(data.get("rows") or [])
    if df.empty:
        return pd.DataFrame()
    df = df[df["session_key"].isin(order)].copy()
    df["race"] = df["session_key"].map(order)
    df["team"] = df["team"].map(team_name)
    cols = [c for c in TEL if c in df]
    return df.groupby(["race", "team"])[cols].mean().reset_index()


def race_index(data, session_key):
    for i, r in enumerate(data.get("races") or []):
        if int(r["session_key"]) == int(session_key):
            return i
    return None


def impact_at(data, events, race, before=3, after=2):
    pace = team_pace(data)
    tel = team_metrics(data)
    here = events[events["race"] == race] if len(events) else events
    out = []
    for _, e in here.iterrows():
        t = e["team"]
        p = pace[pace["team"] == t].set_index("race")["gap"]
        m = tel[tel["team"] == t].set_index("race") if len(tel) else pd.DataFrame()
        b = list(range(race - before, race))
        a = list(range(race, race + after + 1))

        def avg(s, idx):
            v = s.reindex(idx).dropna()
            return float(v.mean()) if len(v) else None

        row = {"team": t, "parts": int(e["parts"]), "items": e["items"], "pace_before": avg(p, b), "pace_here": avg(p, [race]),
               "pace_after": avg(p, a), "races_after": int(p.reindex(a).notna().sum())}
        for c in TEL:
            if len(m) and c in m:
                row[f"{c}_before"], row[f"{c}_after"] = avg(m[c], b), avg(m[c], a)
        out.append(row)
    return out


ADUO = Path(__file__).resolve().parent.parent / "styles" / "aduo_2026.json"


def aduo():
    import json

    try:
        return json.loads(ADUO.read_text())
    except Exception:
        return None


def maker_of(team, a):
    t = team_name(team)
    for m, teams in (a or {}).get("makers", {}).items():
        if t in teams:
            return m
    return None


def maker_speed(data, a):
    races = data.get("races") or []
    locs = [r["location"] for r in races]
    df = pd.DataFrame(data.get("rows") or [])
    if df.empty:
        return pd.DataFrame()
    order = {r["session_key"]: i for i, r in enumerate(races)}
    df = df[df["session_key"].isin(order)].copy()
    df["race"] = df["session_key"].map(order)
    df["maker"] = df["team"].map(lambda t: maker_of(t, a))
    ends = [locs.index(p["end_location"]) for p in a["periods"] if p["end_location"] in locs]
    def period(i):
        for k, e in enumerate(ends):
            if i <= e:
                return k
        return len(ends)
    df["period"] = df["race"].map(period)
    cols = [c for c in ("top_speed_kmh", "late_straight_acc", "clip_kmh") if c in df]
    per_race = df.dropna(subset=["maker"]).groupby(["race", "maker"])[cols].mean().reset_index()
    per_race["period"] = per_race["race"].map(period)
    return per_race
