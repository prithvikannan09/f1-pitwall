import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from f1analytics import config
from f1analytics.sources.openf1_source import _status_windows, _ts

log = logging.getLogger("f1analytics.racecraft")
DATA_DIR = Path(__file__).resolve().parent.parent / "styles"
ATTACK_RANGE_S = 1.0
PIT_WINDOW_S = (-40, 40)
SHRINK_LAPS = 40.0
CLEAR_AIR_S = 2.0
BRAKE_MIN_SPEED = 150.0
BRAKE_MIN_DROP = 60.0
ZONE_MATCH_FRAC = 0.02
FLAT = 98
STRAIGHT_MIN_S = 4.0
MIN_RACES = 3


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def fetch_race(src, session_key, telemetry=True):
    raw = {ep: src._get(ep, session_key=session_key) for ep in
           ("drivers", "laps", "stints", "pit", "race_control", "overtakes", "intervals", "starting_grid", "position", "session_result")}
    raw["session_key"] = int(session_key)
    raw["car_data"] = {}
    if telemetry and not raw["laps"].empty:
        for num, (t0, t1) in telemetry_windows(raw).items():
            raw["car_data"][num] = src._get("car_data", session_key=session_key, driver_number=num,
                                            **{"date>": t0.isoformat(), "date<": t1.isoformat()})
    return raw


def _laps(raw):
    laps = raw["laps"].copy()
    if laps.empty:
        return laps
    laps["start"] = _ts(laps["date_start"])
    laps["dur"] = _num(laps["lap_duration"])
    laps["end"] = laps["start"] + pd.to_timedelta(laps["dur"], unit="s")
    laps["driver_number"] = laps["driver_number"].astype(int)
    total = int(laps["lap_number"].max())
    windows = _status_windows(raw.get("race_control"))
    neutral = pd.Series(False, index=laps.index)
    for t0, t1, _ in windows:
        neutral |= (laps["start"] < t1) & (laps["end"] > t0)
    laps["neutral"] = neutral
    pits = raw.get("pit")
    pit_laps = set()
    if pits is not None and not pits.empty:
        pit_laps = set(zip(pits["driver_number"].astype(int), pits["lap_number"].astype(int)))
    laps["pit_in"] = [(n, int(l)) in pit_laps for n, l in zip(laps["driver_number"], laps["lap_number"])]
    laps["pit_out"] = laps["is_pit_out_lap"].fillna(False).astype(bool)
    fuel_per_lap = config.FUEL_SEC_PER_KG * config.START_FUEL_KG / max(total, 1)
    laps["corr"] = laps["dur"] - fuel_per_lap * (total - laps["lap_number"])
    clean = (laps["lap_number"] > 1) & ~laps["neutral"] & ~laps["pit_in"] & ~laps["pit_out"] & laps["dur"].notna()
    med = laps[clean].groupby("driver_number")["dur"].transform("median")
    laps["clean"] = False
    laps.loc[med.index, "clean"] = laps.loc[med.index, "dur"] < med * 1.07
    laps["total"] = total
    return laps


def _gaps_at_lap_end(raw, laps):
    iv = raw.get("intervals")
    if iv is None or iv.empty:
        return pd.DataFrame()
    iv = iv.assign(t=_ts(iv["date"]), interval=_num(iv["interval"]), gap=_num(iv["gap_to_leader"]), driver_number=iv["driver_number"].astype(int))
    iv = iv.dropna(subset=["t"]).sort_values("t")
    ends = laps.dropna(subset=["end"])[["driver_number", "lap_number", "end", "clean", "neutral", "pit_in", "pit_out"]].sort_values("end")
    out = pd.merge_asof(ends, iv[["t", "driver_number", "interval", "gap"]], left_on="end", right_on="t", by="driver_number", direction="backward",
                        tolerance=pd.Timedelta(seconds=20))
    return out


def _pit_windows(raw, laps=None):
    pits = raw.get("pit")
    out = {}
    if pits is None or pits.empty:
        return out
    pits = pits.assign(t=_ts(pits["date"]), d=_num(pits.get("pit_duration")).fillna(25))
    outlap_end = {}
    if laps is not None and not laps.empty:
        po = laps[laps["pit_out"]].dropna(subset=["end"])
        for n, g in po.groupby("driver_number"):
            outlap_end[int(n)] = sorted(g["end"])
    for _, p in pits.iterrows():
        n = int(p["driver_number"])
        t0 = p["t"] + pd.Timedelta(seconds=PIT_WINDOW_S[0])
        t1 = p["t"] + pd.Timedelta(seconds=PIT_WINDOW_S[1] + p["d"])
        later = [e for e in outlap_end.get(n, []) if e > p["t"]]
        if later:
            t1 = max(t1, later[0] + pd.Timedelta(seconds=5))
        out.setdefault(n, []).append((t0, t1))
    return out


def _on_track_passes(raw, laps):
    ov = raw.get("overtakes")
    if ov is None or ov.empty:
        return pd.DataFrame(columns=["by", "on", "t"])
    ov = ov.assign(t=_ts(ov["date"]), by=ov["overtaking_driver_number"].astype(int), on=ov["overtaken_driver_number"].astype(int))
    windows = _pit_windows(raw, laps)
    lap2 = laps[laps["lap_number"] == 2]["start"].min()
    neutral = _status_windows(raw.get("race_control"))
    def ok(r):
        if pd.notna(lap2) and r["t"] < lap2:
            return False
        if any(t0 <= r["t"] <= t1 for t0, t1, _ in neutral):
            return False
        for n in (r["by"], r["on"]):
            if any(a <= r["t"] <= b for a, b in windows.get(n, [])):
                return False
        return True
    ov = ov[ov.apply(ok, axis=1)].sort_values("t")
    ov = ov[~(ov.duplicated(["by", "on"], keep="first") & (ov.groupby(["by", "on"])["t"].diff() < pd.Timedelta(seconds=5)))]
    return ov[["by", "on", "t"]]


def _grid(raw):
    grid = raw.get("starting_grid")
    if grid is not None and not grid.empty:
        return dict(zip(grid["driver_number"].astype(int), _num(grid["position"])))
    pos = raw.get("position")
    if pos is None or pos.empty:
        return {}
    pos = pos.assign(t=_ts(pos["date"]), driver_number=pos["driver_number"].astype(int))
    first = pos[pos["t"] == pos["t"].min()]
    return dict(zip(first["driver_number"], _num(first["position"])))


def _lap1_gain(raw, laps):
    pos = raw.get("position")
    g = _grid(raw)
    if not g or pos is None or pos.empty:
        return {}
    lap2 = laps[laps["lap_number"] == 2]["start"].min()
    if pd.isna(lap2):
        return {}
    pos = pos.assign(t=_ts(pos["date"]), driver_number=pos["driver_number"].astype(int))
    after = pos[pos["t"] <= lap2].sort_values("t").groupby("driver_number")["position"].last()
    return {n: float(g[n] - p) for n, p in after.items() if n in g and pd.notna(g[n])}


def _tyre_wear(raw, laps):
    st = raw.get("stints")
    if st is None or st.empty:
        return {}
    rows = []
    for _, s in st.iterrows():
        n = int(s["driver_number"])
        m = (laps["driver_number"] == n) & laps["lap_number"].between(s["lap_start"], s["lap_end"]) & laps["clean"]
        d = laps[m]
        if len(d) < 8:
            continue
        age = d["lap_number"] - s["lap_start"] + (s.get("tyre_age_at_start") or 0)
        slope = np.polyfit(age, d["corr"], 1)[0]
        rows.append({"n": n, "compound": str(s["compound"]).upper(), "slope": slope, "laps": len(d)})
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    df["rel"] = df["slope"] - df.groupby("compound")["slope"].transform("median")
    return {n: float(np.average(g["rel"], weights=g["laps"])) for n, g in df.groupby("n")}


def race_metrics(raw):
    laps = _laps(raw)
    if laps.empty:
        return []
    drivers = raw["drivers"].drop_duplicates("driver_number")
    codes = dict(zip(drivers["driver_number"].astype(int), drivers["name_acronym"]))
    teams = dict(zip(drivers["driver_number"].astype(int), drivers["team_name"]))
    gaps = _gaps_at_lap_end(raw, laps)
    attack, pressure = {}, {}
    if not gaps.empty:
        usable = gaps[(gaps["lap_number"] > 1) & ~gaps["neutral"] & ~gaps["pit_in"] & ~gaps["pit_out"]]
        for lap, g in usable.dropna(subset=["gap"]).groupby("lap_number"):
            g = g.sort_values("gap")
            order = g["driver_number"].tolist()
            ivs = g["interval"].tolist()
            for i in range(1, len(order)):
                if pd.notna(ivs[i]) and ivs[i] < ATTACK_RANGE_S:
                    attack[order[i]] = attack.get(order[i], 0) + 1
                    pressure[order[i - 1]] = pressure.get(order[i - 1], 0) + 1
    passes = _on_track_passes(raw, laps)
    made = passes["by"].value_counts().to_dict()
    lost = passes["on"].value_counts().to_dict()
    lap1 = _lap1_gain(raw, laps)
    wear = _tyre_wear(raw, laps)
    clean = laps[laps["clean"]]
    pace = clean.groupby("driver_number")["corr"].median()
    best = pace.min() if len(pace) else np.nan
    res = raw.get("session_result")
    finish = dict(zip(res["driver_number"].astype(int), _num(res["position"]))) if res is not None and not res.empty else {}
    start = _grid(raw)
    tele = telemetry_metrics(raw, laps) if raw.get("car_data") else {}
    first_tyre = {}
    st = raw.get("stints")
    if st is not None and not st.empty:
        f = st.sort_values("stint_number").groupby("driver_number").first()
        first_tyre = {int(n): str(c).upper() for n, c in f["compound"].items() if pd.notna(c)}
    out = []
    for n in sorted(set(laps["driver_number"])):
        if n not in codes:
            continue
        out.append({
            "session_key": raw.get("session_key"), "number": n, "code": codes[n], "team": teams.get(n),
            "attack_laps": attack.get(n, 0), "pressure_laps": pressure.get(n, 0),
            "passes_made": int(made.get(n, 0)), "passes_lost": int(lost.get(n, 0)),
            "lap1_gain": lap1.get(n), "wear_rel": wear.get(n),
            "pace_pct": float((pace[n] - best) / best * 100) if n in pace.index and pd.notna(best) else None,
            "clean_laps": int((clean["driver_number"] == n).sum()),
            "grid": start.get(n), "finish": finish.get(n),
            "start_tyre": first_tyre.get(n),
            **tele.get(n, {}),
        })
    return out


def telemetry_windows(raw):
    laps = _laps(raw)
    gaps = _gaps_at_lap_end(raw, laps)
    if laps.empty:
        return {}
    clear = set()
    if not gaps.empty:
        clear = set(zip(gaps.loc[gaps["interval"].isna() | (gaps["interval"] > CLEAR_AIR_S), "driver_number"], gaps.loc[gaps["interval"].isna() | (gaps["interval"] > CLEAR_AIR_S), "lap_number"]))
    out = {}
    for n, d in laps[laps["clean"]].groupby("driver_number"):
        d = d.sort_values("lap_number")
        ok = d[[(n, l) in clear for l in d["lap_number"]]] if clear else d
        pick = ok if len(ok) >= 2 else d
        pick = pick.nsmallest(3, "corr").sort_values("lap_number")
        if pick.empty:
            continue
        r = pick.iloc[0]
        out[int(n)] = (r["start"] - pd.Timedelta(seconds=1), r["end"] + pd.Timedelta(seconds=1))
    return out


def _lap_trace(car, t0, t1):
    c = car.assign(t=_ts(car["date"]))
    c = c[(c["t"] >= t0) & (c["t"] <= t1)].sort_values("t")
    if len(c) < 50:
        return None
    sec = (c["t"] - c["t"].iloc[0]).dt.total_seconds().to_numpy()
    v = _num(c["speed"]).to_numpy(dtype=float)
    dist = np.concatenate([[0], np.cumsum((v[1:] + v[:-1]) / 2 / 3.6 * np.diff(sec))])
    return pd.DataFrame({"s": sec, "v": v, "d": dist, "thr": _num(c["throttle"]).to_numpy(dtype=float),
                         "brk": (_num(c["brake"]).fillna(0) > 0).to_numpy()})


def _brake_zones(tr):
    zones, i, n = [], 1, len(tr)
    while i < n:
        if tr["brk"].iat[i] and not tr["brk"].iat[i - 1] and tr["v"].iat[i - 1] >= BRAKE_MIN_SPEED:
            j = i
            while j + 1 < n and (tr["brk"].iat[j + 1] or tr["v"].iat[j + 1] < tr["v"].iat[j]):
                j += 1
            seg = tr.iloc[i - 1:j + 1]
            k = seg["v"].idxmin()
            v0, vmin = tr["v"].iat[i - 1], tr["v"].at[k]
            if v0 - vmin >= BRAKE_MIN_DROP:
                zones.append({"start": tr["d"].iat[i - 1], "v0": v0, "vmin": vmin, "len": tr["d"].at[k] - tr["d"].iat[i - 1]})
            i = j + 1
        i += 1
    return zones


def _straights(tr):
    out, i, n = [], 0, len(tr)
    while i < n:
        if tr["thr"].iat[i] >= FLAT:
            j = i
            while j + 1 < n and tr["thr"].iat[j + 1] >= FLAT:
                j += 1
            seg = tr.iloc[i:j + 1]
            if seg["s"].iat[-1] - seg["s"].iat[0] >= STRAIGHT_MIN_S:
                cut = seg["s"].iat[0] + 0.6 * (seg["s"].iat[-1] - seg["s"].iat[0])
                late = seg[seg["s"] >= cut]
                acc = (late["v"].iat[-1] - late["v"].iat[0]) / max(late["s"].iat[-1] - late["s"].iat[0], 0.1)
                out.append({"start": seg["d"].iat[0], "top": seg["v"].max(), "late_acc": acc, "clip": seg["v"].max() - seg["v"].iat[-1]})
            i = j
        i += 1
    return out


def telemetry_metrics(raw, laps):
    windows = telemetry_windows(raw)
    per = {}
    for n, car in (raw.get("car_data") or {}).items():
        if car is None or car.empty or int(n) not in windows:
            continue
        tr = _lap_trace(car, *windows[int(n)])
        if tr is None:
            continue
        L = tr["d"].iat[-1]
        per[int(n)] = {"L": L, "zones": [dict(z, f=z["start"] / L) for z in _brake_zones(tr)],
                       "straights": [dict(s, f=s["start"] / L) for s in _straights(tr)]}
    if len(per) < 6:
        return {}
    lap_len = float(np.median([p["L"] for p in per.values()]))
    ref_z = _reference(per, "zones")
    ref_s = _reference(per, "straights")
    out = {}
    for n, p in per.items():
        late, carry, top, acc, clip = [], [], [], [], []
        for z in p["zones"]:
            r = _match(ref_z, z["f"])
            if r is None:
                continue
            late.append((z["f"] - r["f"]) * lap_len)
            carry.append(z["vmin"] - r["vmin"])
        for s in p["straights"]:
            r = _match(ref_s, s["f"])
            if r is None:
                continue
            top.append(s["top"] - r["top"])
            acc.append(s["late_acc"] - r["late_acc"])
            clip.append(s["clip"] - r["clip"])
        def med(x):
            return float(np.median(x)) if len(x) >= 2 else None
        out[n] = {"brake_later_m": med(late), "corner_speed_kmh": med(carry), "top_speed_kmh": med(top),
                  "late_straight_acc": med(acc), "clip_kmh": med(clip), "brake_zones": len(late)}
    return out


def _reference(per, kind):
    pts = sorted((x for p in per.values() for x in p[kind]), key=lambda x: x["f"])
    groups = []
    for x in pts:
        if groups and x["f"] - groups[-1][-1]["f"] <= ZONE_MATCH_FRAC:
            groups[-1].append(x)
        else:
            groups.append([x])
    need = max(4, len(per) // 2)
    return [{k: float(np.median([x[k] for x in g])) for k in g[0] if isinstance(g[0][k], (int, float, np.floating))} for g in groups if len(g) >= need]


def _match(ref, f):
    best = min(ref, key=lambda r: abs(r["f"] - f), default=None)
    return best if best is not None and abs(best["f"] - f) <= ZONE_MATCH_FRAC else None


def build_season(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return {}
    races = df.groupby("code")["session_key"].nunique()
    field_conv = df["passes_made"].sum() / max(df["attack_laps"].sum(), 1)
    field_leak = df["passes_lost"].sum() / max(df["pressure_laps"].sum(), 1)
    out = {}
    for code, g in df.groupby("code"):
        a, p = g["attack_laps"].sum(), g["pressure_laps"].sum()
        conv = (g["passes_made"].sum() + SHRINK_LAPS * field_conv) / (a + SHRINK_LAPS)
        leak = (g["passes_lost"].sum() + SHRINK_LAPS * field_leak) / (p + SHRINK_LAPS)
        def avg(col):
            v = _num(g[col]).dropna() if col in g else pd.Series(dtype=float)
            return float(v.mean()) if len(v) else None

        def m(col):
            s = _num(g[col]) if col in g else pd.Series(dtype=float)
            s = s.dropna()
            return float(s.median()) if len(s) else None
        out[code] = {
            "code": code, "team": g.sort_values("session_key")["team"].iloc[-1], "races": int(races[code]),
            "attack_laps": int(a), "pressure_laps": int(p),
            "passes_made": int(g["passes_made"].sum()), "passes_lost": int(g["passes_lost"].sum()),
            "attack_conv": float(conv), "defence_hold": float(1 - leak),
            "lap1_gain": avg("lap1_gain"), "wear_rel": m("wear_rel"), "pace_pct": m("pace_pct"),
            "places_gained": m("gained") if "gained" in g else None,
            "brake_later_m": m("brake_later_m"), "corner_speed_kmh": m("corner_speed_kmh"),
            "top_speed_kmh": m("top_speed_kmh"), "late_straight_acc": m("late_straight_acc"), "clip_kmh": m("clip_kmh"),
        }
    df["gained"] = _num(df["grid"]) - _num(df["finish"])
    for code, g in df.groupby("code"):
        s = g["gained"].dropna()
        out[code]["places_gained"] = float(s.mean()) if len(s) else None
    _teammate_deltas(out)
    _percentiles(out)
    for v in out.values():
        v["tags"] = style_tags(v)
    return out


def _teammate_deltas(profiles):
    by_team = {}
    for p in profiles.values():
        by_team.setdefault(p["team"], []).append(p)
    for mates in by_team.values():
        for p in mates:
            other = next((m for m in mates if m["code"] != p["code"] and m["races"] >= MIN_RACES), None)
            p["teammate"] = other["code"] if other else None
            for k in ("brake_later_m", "top_speed_kmh", "late_straight_acc", "corner_speed_kmh", "pace_pct"):
                p[f"{k}_vs_mate"] = (p[k] - other[k]) if other and p.get(k) is not None and other.get(k) is not None else None


SCORES = {
    "attack": ("attack_conv", 1), "defence": ("defence_hold", 1), "starts": ("lap1_gain", 1),
    "tyres": ("wear_rel", -1), "pace": ("pace_pct", -1), "braking": ("brake_later_m", 1), "straights": ("late_straight_acc", 1),
}


def _percentiles(profiles):
    pool = [p for p in profiles.values() if p["races"] >= MIN_RACES]
    for name, (key, sign) in SCORES.items():
        vals = sorted(sign * p[key] for p in pool if p.get(key) is not None)
        for p in profiles.values():
            v = p.get(key)
            if v is None or not vals or p["races"] < MIN_RACES:
                p[f"{name}_score"] = None
                continue
            below = sum(1 for x in vals if x < sign * v)
            equal = sum(1 for x in vals if x == sign * v)
            p[f"{name}_score"] = round(100 * (below + 0.5 * equal) / len(vals))


TAGS = [
    ("attack_score", 75, "Hunter", "turns 'within a second' into a pass more often than most"),
    ("defence_score", 75, "The wall", "very hard to pass once he is ahead"),
    ("starts_score", 75, "Rocket starts", "usually gains places on lap 1"),
    ("tyres_score", 75, "Tyre whisperer", "his tyres wear slower than the field's"),
    ("pace_score", 80, "Race-pace king", "one of the fastest over a full race"),
    ("braking_score", 75, "Late braker", "hits the brakes later than most into big stops"),
    ("straights_score", 75, "Strong on the straights", "keeps pulling hard late on the straights (battery deployment)"),
]


def style_tags(p):
    tags = [(name, why) for key, cut, name, why in TAGS if (p.get(key) or 0) >= cut]
    if p.get("defence_score") is not None and p["defence_score"] <= 20:
        tags.append(("Can be passed", "loses places more often than most when a car is within a second"))
    if p.get("attack_score") is not None and p["attack_score"] <= 20:
        tags.append(("Patient", "rarely forces a pass on track; gains come from strategy"))
    return [{"name": n, "why": w} for n, w in tags]


def build(year, src=None, telemetry=True, out_dir=None, before=None):
    from f1analytics.sources.openf1_source import OpenF1Source

    src = src or OpenF1Source()
    sessions = src._get("sessions", year=int(year), session_name="Race")
    now = pd.Timestamp.utcnow().tz_localize(None) if before is None else pd.Timestamp(before)
    sessions = sessions.assign(t=_ts(sessions["date_end"])).sort_values("t")
    sessions = sessions[sessions["t"] < now]
    rows, races = [], []
    for _, s in sessions.iterrows():
        try:
            raw = fetch_race(src, s["session_key"], telemetry=telemetry)
            r = race_metrics(raw)
        except Exception as exc:
            log.warning("skip %s: %s", s.get("location"), exc)
            continue
        if not r:
            continue
        rows += r
        races.append({"session_key": int(s["session_key"]), "location": s.get("location"), "date": str(s["date_start"])[:10]})
        log.info("%s: %d drivers", s.get("location"), len(r))
    profiles = build_season(rows)
    data = {"year": int(year), "built": pd.Timestamp.utcnow().isoformat(), "races": races, "rows": rows, "profiles": profiles, "start_tyres": start_tyre_stats(rows)}
    out_dir = Path(out_dir or DATA_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"racecraft_{year}.json").write_text(json.dumps(data, default=_json, indent=1))
    return data


def _json(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    return str(o)


def load(year=2026):
    path = DATA_DIR / f"racecraft_{year}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


H2H_RUNS = 4000
LAP_NOISE_S = 0.25
STRATEGY_NOISE_S = 2.5


def _car(snapshot, code):
    return next((d for d in (snapshot or {}).get("drivers", []) if d.get("code") == code), None)


def _recent_pace(snapshot, code, n=8):
    from f1analytics.pitwall.engine import laps_frame, total_laps

    df = laps_frame(snapshot)
    if df.empty:
        return None
    total = total_laps(snapshot) or 60
    d = df[(df["Driver"] == code) & df["IsAccurate"]].sort_values("LapNumber").tail(n)
    if len(d) < 4:
        return None
    k = config.FUEL_SEC_PER_KG * config.START_FUEL_KG / total
    t = d["LapTime"].dt.total_seconds() - k * (total - d["LapNumber"])
    return float(t.median())


def _plan(snapshot, car, pit_loss=None):
    from f1analytics.pitwall.engine import analyse

    try:
        res = analyse(snapshot, team=car.get("team") or "", pit_loss=pit_loss)
    except Exception:
        return None
    r = next((x for x in res["cars"] if x["car"]["code"] == car["code"]), None)
    return r["best_plan"] if r else None


def _track_word(score):
    if score <= -0.15:
        return "quicker than his norm here"
    if score >= 0.15:
        return "slower than his norm here"
    return "about his normal pace here"


def head_to_head(snapshot, profiles, a, b, seed=11, track=None):
    pa, pb = (profiles or {}).get(a), (profiles or {}).get(b)
    ca, cb = _car(snapshot, a), _car(snapshot, b)
    session = (snapshot or {}).get("session") or {}
    race = str(session.get("type") or "").lower() in ("race", "sprint")
    track = track or session.get("circuit")
    reasons = []
    field_leak = 1 - float(np.median([p["defence_hold"] for p in profiles.values()])) if profiles else 0.15
    def per_lap_pass(t, l):
        conv = (t or {}).get("attack_conv", 0.05)
        leak = 1 - (l or {}).get("defence_hold", 1 - field_leak)
        return float(min(0.5, conv * leak / max(field_leak, 1e-3)))
    rng = np.random.default_rng(seed)
    source = "season"
    if race and ca and cb and ca.get("gap_to_leader") is not None and cb.get("gap_to_leader") is not None and not ca.get("retired") and not cb.get("retired"):
        plan_a, plan_b = _plan(snapshot, ca), _plan(snapshot, cb)
        laps_left = max(int((session.get("total_laps") or 0) - (ca.get("laps") or 0)), 0)
        gap_now = float(cb["gap_to_leader"] - ca["gap_to_leader"])
        if plan_a and plan_b and laps_left > 0:
            source = "today"
            swing = plan_b["total"] - plan_a["total"]
            stops = plan_a["stops"] + plan_b["stops"]
            sd = LAP_NOISE_S * np.sqrt(laps_left) + (STRATEGY_NOISE_S if stops else 0.5)
            final = gap_now + swing + rng.normal(0, sd, H2H_RUNS)
            ra, rb = _recent_pace(snapshot, a), _recent_pace(snapshot, b)
            if ra and rb:
                reasons.append(f"Recent race pace: {a} {'faster' if ra < rb else 'slower'} by {abs(ra - rb):.2f}s a lap (fuel-corrected).")
            reasons.append(f"Gap now: {a} is {'ahead' if gap_now > 0 else 'behind'} by {abs(gap_now):.1f}s with {laps_left} laps to go.")
            reasons.append(f"Strategy from here: {a} {plan_a['stops']} stop(s), {b} {plan_b['stops']} stop(s); projected swing {swing:+.1f}s to {a}.")
        else:
            final, laps_left, gap_now = None, laps_left, gap_now
    else:
        final, laps_left, gap_now = None, int(session.get("total_laps") or 57), 0.0
    if final is None:
        if not (pa and pb) or pa.get("pace_pct") is None or pb.get("pace_pct") is None:
            return None
        lap_s = 90.0
        per_lap = (pb["pace_pct"] - pa["pace_pct"]) / 100 * lap_s
        aff = track_affinity((load_history() or {}).get("rows", [])) if track else None
        ta, tb = affinity_at(aff, a, track), affinity_at(aff, b, track)
        if ta and tb:
            per_lap += (tb["score"] - ta["score"]) / 100 * lap_s * 0.5
            reasons.append(f"At {track}: {a} is usually {_track_word(ta['score'])} ({ta['visits']} visits), {b} {_track_word(tb['score'])} ({tb['visits']} visits).")
        sd = LAP_NOISE_S * np.sqrt(laps_left) + STRATEGY_NOISE_S + 3.0
        final = gap_now + per_lap * laps_left + rng.normal(0, sd, H2H_RUNS)
        reasons.append(f"Season race pace: {a} averages {abs(per_lap):.2f}s a lap {'quicker' if per_lap > 0 else 'slower'} than {b}.")
    a_ahead_now = gap_now >= 0
    trailing, leading = (b, a) if a_ahead_now else (a, b)
    p = per_lap_pass(profiles.get(trailing) if profiles else None, profiles.get(leading) if profiles else None)
    a_wins = np.zeros(H2H_RUNS, dtype=bool)
    for i, g in enumerate(final):
        lead_final = g if a_ahead_now else -g
        if lead_final >= 0 or abs(gap_now) < 0.05:
            a_wins[i] = (g >= 0)
            continue
        catch_frac = abs(gap_now) / (abs(gap_now) + abs(lead_final))
        n = max(0, int(round(laps_left * (1 - catch_frac))))
        passed = rng.random() < 1 - (1 - p) ** n
        trailing_wins = passed
        a_wins[i] = trailing_wins if not a_ahead_now else not trailing_wins
    prob = float(a_wins.mean())
    pace_only = float((final >= 0).mean())
    if pa and pb:
        at, df = profiles[trailing].get("attack_score"), profiles[leading].get("defence_score")
        if at is not None and df is not None:
            lead_in = f"Racecraft: {trailing} (behind) has an attack score of {at}/100, {leading} (ahead) a defence score of {df}/100. " if abs(gap_now) >= 0.05 else \
                f"Racecraft if they meet on track: {a} attack {profiles[a].get('attack_score')}/defence {profiles[a].get('defence_score')}, {b} attack {profiles[b].get('attack_score')}/defence {profiles[b].get('defence_score')}. "
            reasons.append(lead_in + ("" if abs(gap_now) < 0.05 else ("Expect the move to come." if at > df + 15 else ("Hard to get past him." if df > at + 15 else "An even fight if they meet on track."))))
    return {"a": a, "b": b, "prob": prob, "pace_only": pace_only, "source": source, "reasons": reasons, "per_lap_pass": p}


def start_tyre_stats(rows):
    df = pd.DataFrame(rows)
    if df.empty or "start_tyre" not in df:
        return {}
    df["lap1_gain"] = _num(df["lap1_gain"])
    out = {}
    for c, g in df.dropna(subset=["start_tyre", "lap1_gain"]).groupby("start_tyre"):
        out[c] = {"starts": int(len(g)), "lap1_gain": float(g["lap1_gain"].mean())}
    return out


HISTORY_YEARS = (2023, 2024, 2025, 2026)
TRACK_MIN_VISITS = 2


def history_rows(raw, year, location):
    laps = _laps(raw)
    if laps.empty:
        return []
    drivers = raw["drivers"].drop_duplicates("driver_number")
    codes = dict(zip(drivers["driver_number"].astype(int), drivers["name_acronym"]))
    teams = dict(zip(drivers["driver_number"].astype(int), drivers["team_name"]))
    clean = laps[laps["clean"]]
    pace = clean.groupby("driver_number")["corr"].median()
    counts = clean.groupby("driver_number").size()
    if pace.empty:
        return []
    best = pace.min()
    res = raw.get("session_result")
    finish = dict(zip(res["driver_number"].astype(int), _num(res["position"]))) if res is not None and not res.empty else {}
    grid = _grid(raw)
    out = []
    for n, p in pace.items():
        if n not in codes or counts.get(n, 0) < 10:
            continue
        out.append({"year": int(year), "location": location, "code": codes[n], "team": teams.get(n),
                    "pace_pct": float((p - best) / best * 100), "finish": finish.get(n), "grid": grid.get(n)})
    return out


def build_history(years=HISTORY_YEARS, src=None, out_dir=None):
    from f1analytics.sources.openf1_source import OpenF1Source

    src = src or OpenF1Source()
    now = pd.Timestamp.utcnow().tz_localize(None)
    rows = []
    for year in years:
        sessions = src._get("sessions", year=int(year), session_name="Race")
        if sessions.empty:
            continue
        sessions = sessions.assign(t=_ts(sessions["date_end"])).sort_values("t")
        for _, s in sessions[sessions["t"] < now].iterrows():
            try:
                raw = {ep: src._get(ep, session_key=s["session_key"]) for ep in ("drivers", "laps", "pit", "race_control", "session_result", "position", "starting_grid")}
                r = history_rows(raw, year, s.get("circuit_short_name") or s.get("location"))
            except Exception as exc:
                log.warning("skip %s %s: %s", year, s.get("location"), exc)
                continue
            rows += r
            log.info("%s %s: %d drivers", year, s.get("location"), len(r))
    data = {"built": pd.Timestamp.utcnow().isoformat(), "years": list(years), "rows": rows}
    out_dir = Path(out_dir or DATA_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "track_history.json").write_text(json.dumps(data, default=_json, indent=1))
    return data


def track_affinity(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return {}
    df["pace_pct"] = _num(df["pace_pct"])
    df["season_norm"] = df.groupby(["code", "year"])["pace_pct"].transform("median")
    df["vs_norm"] = df["pace_pct"] - df["season_norm"]
    mate = df.groupby(["year", "location", "team"])["pace_pct"].transform(lambda s: s.sum())
    size = df.groupby(["year", "location", "team"])["pace_pct"].transform("size")
    df["vs_mate"] = np.where(size == 2, df["pace_pct"] - (mate - df["pace_pct"]), np.nan)
    df["mate_norm"] = df.groupby(["code", "year"])["vs_mate"].transform("median")
    df["vs_mate_norm"] = df["vs_mate"] - df["mate_norm"]
    df["score"] = df[["vs_norm", "vs_mate_norm"]].mean(axis=1, skipna=True)
    out = {}
    for code, g in df.groupby("code"):
        tracks = []
        for loc, t in g.groupby("location"):
            tracks.append({"location": loc, "visits": int(len(t)), "score": float(t["score"].mean()),
                           "best_finish": None if t["finish"].dropna().empty else int(_num(t["finish"]).min()),
                           "finishes": [None if pd.isna(f) else int(f) for f in _num(t.sort_values("year")["finish"])],
                           "years": [int(y) for y in t.sort_values("year")["year"]]})
        solid = [t for t in tracks if t["visits"] >= TRACK_MIN_VISITS] or tracks
        solid.sort(key=lambda t: t["score"])
        out[code] = {"tracks": sorted(tracks, key=lambda t: t["score"]), "best": solid[:3], "worst": list(reversed(solid[-3:])) if len(solid) > 3 else []}
    return out


def load_history():
    path = DATA_DIR / "track_history.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def affinity_at(aff, code, location):
    if not aff or code not in aff or not location:
        return None
    key = str(location).lower()
    return next((t for t in aff[code]["tracks"] if str(t["location"]).lower() in key or key in str(t["location"]).lower()), None)


def refresh_profiles(year=2026):
    data = load(year)
    if not data:
        return None
    data["profiles"] = build_season(data["rows"])
    data["start_tyres"] = start_tyre_stats(data["rows"])
    data["races"] = [r for r in data["races"] if any(x["session_key"] == r["session_key"] for x in data["rows"])]
    (DATA_DIR / f"racecraft_{year}.json").write_text(json.dumps(data, default=_json, indent=1))
    return data


def podium_table(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame()
    df["finish"] = _num(df["finish"])
    df["grid"] = _num(df["grid"])
    df["pace_pct"] = _num(df["pace_pct"])
    df["expected"] = df.groupby("session_key")["pace_pct"].rank(method="min")
    done = df.dropna(subset=["finish"])
    out = done.groupby("code").agg(
        races=("session_key", "nunique"),
        wins=("finish", lambda s: int((s == 1).sum())),
        podiums=("finish", lambda s: int((s <= 3).sum())),
        avg_finish=("finish", "mean"),
    )
    gained = (done["grid"] - done["finish"]).groupby(done["code"]).mean()
    above = (done["expected"] - done["finish"]).groupby(done["code"]).mean()
    out["gained"] = gained
    out["above_car"] = above
    pairs = done.groupby(["session_key", "team"]).filter(lambda g: len(g) == 2)
    pairs = pairs.assign(beat=pairs.groupby(["session_key", "team"])["finish"].transform(lambda s: (s == s.min()).astype(float)))
    out["beat_mate"] = pairs.groupby("code")["beat"].mean() * 100
    return out.reset_index().sort_values(["podiums", "above_car"], ascending=[False, False])
