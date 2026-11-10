import re

import numpy as np
import pandas as pd

DRY = ("SOFT", "MEDIUM", "HARD")
HARDNESS = {"SOFT": 0, "MEDIUM": 1, "HARD": 2, "INTERMEDIATE": 3, "WET": 4}
SHORT = {"SOFT": "S", "MEDIUM": "M", "HARD": "H", "INTERMEDIATE": "I", "WET": "W"}
ALLOCATION = {"standard": {"SOFT": 8, "MEDIUM": 3, "HARD": 2}, "sprint": {"SOFT": 6, "MEDIUM": 4, "HARD": 2}}
NEUTRAL_FACTOR = 1.10
MIN_LAPS = 3
RED_PIT_S = 120.0


def _ts(series):
    t = pd.to_datetime(series, utc=True, errors="coerce", format="mixed")
    return t.dt.tz_convert(None)


def _df(raw, key):
    v = raw.get(key)
    return v.copy() if isinstance(v, pd.DataFrame) else pd.DataFrame()


def codes(raw):
    d = _df(raw, "drivers")
    if d.empty:
        return {}
    d = d.drop_duplicates("driver_number", keep="last")
    return {int(n): str(c) for n, c in zip(d["driver_number"], d["name_acronym"])}


def colours(raw):
    d = _df(raw, "drivers")
    if d.empty or "team_colour" not in d:
        return {}
    d = d.drop_duplicates("driver_number", keep="last")
    return {int(n): f"#{str(c).lstrip('#')}" if isinstance(c, str) and c else "#888888" for n, c in zip(d["driver_number"], d["team_colour"])}


def teams(raw):
    d = _df(raw, "drivers")
    if d.empty or "team_name" not in d:
        return {}
    d = d.drop_duplicates("driver_number", keep="last")
    return {int(n): str(t) for n, t in zip(d["driver_number"], d["team_name"])}


def _stint_at(stints, num, lap):
    s = stints[(stints["driver_number"] == num) & (stints["lap_start"] <= lap) & (stints["lap_end"] >= lap)]
    return s.iloc[-1] if len(s) else None


def neutral_from_race_control(rc, last_lap, slow=None):
    if rc is None or len(rc) == 0 or "message" not in rc:
        return None
    msgs = rc.dropna(subset=["message"]).copy()
    msgs["lap_number"] = pd.to_numeric(msgs.get("lap_number"), errors="coerce")
    if "date" in msgs:
        msgs = msgs.sort_values("date")
    out, start = set(), None
    for lap, m in zip(msgs["lap_number"], msgs["message"].astype(str).str.upper()):
        if pd.isna(lap):
            continue
        lap = int(lap)
        if "SAFETY CAR DEPLOYED" in m or "VSC DEPLOYED" in m or m.startswith("RED FLAG"):
            start = lap if start is None else start
        elif start is not None and ("IN THIS LAP" in m or "ENDING" in m or "GREEN LIGHT" in m or "RESUME" in m):
            out.update(range(start, lap + 1))
            start = None
    if start is not None:
        lap = start
        out.add(lap)
        while lap + 1 <= int(last_lap) and slow is not None and (lap + 1) in slow:
            lap += 1
            out.add(lap)
    return out


def neutral_laps(laps, rc=None):
    x = laps.dropna(subset=["lap_duration"])
    last = int(x["lap_number"].max()) if len(x) else 0
    from_rc = neutral_from_race_control(rc, last, _slow_laps(x))
    if from_rc is not None:
        return from_rc
    return _slow_laps(x)


def _slow_laps(x):
    if "pit_in" in x:
        x = x[~x["pit_in"] & ~x["pit_out"]]
    g = x.groupby("lap_number")["lap_duration"].median()
    if g.empty:
        return set()
    base = g[g.index > 1].median()
    out = {int(n) for n, v in g.items() if n > 1 and v > base * NEUTRAL_FACTOR}
    return out


def lap_table(raw):
    laps = _df(raw, "laps")
    if laps.empty:
        return laps
    stints, pits = _df(raw, "stints"), _df(raw, "pit")
    laps = laps.dropna(subset=["lap_number"]).copy()
    laps["driver_number"] = laps["driver_number"].astype(int)
    laps["lap_number"] = laps["lap_number"].astype(int)
    laps["lap_duration"] = pd.to_numeric(laps["lap_duration"], errors="coerce")
    laps["t"] = _ts(laps["date_start"]) if "date_start" in laps else pd.NaT
    pit_in = {(int(a), int(b)) for a, b in zip(pits.get("driver_number", []), pits.get("lap_number", []))} if not pits.empty else set()
    comp, age, new = [], [], []
    for n, lap in zip(laps["driver_number"], laps["lap_number"]):
        s = _stint_at(stints, n, lap) if not stints.empty else None
        if s is None:
            comp.append(None), age.append(np.nan), new.append(None)
            continue
        a0 = s.get("tyre_age_at_start")
        a0 = 0 if pd.isna(a0) else int(a0)
        comp.append(str(s.get("compound") or "").upper() or None)
        age.append(a0 + lap - int(s["lap_start"]))
        new.append(a0 == 0)
    laps["compound"], laps["tyre_age"], laps["new_set"] = comp, age, new
    laps["pit_in"] = np.array([(n, l) in pit_in for n, l in zip(laps["driver_number"], laps["lap_number"])], dtype=bool)
    out_lap = laps["is_pit_out_lap"].fillna(False).astype(bool) if "is_pit_out_lap" in laps else False
    laps["pit_out"] = out_lap | np.array([(n, l - 1) in pit_in for n, l in zip(laps["driver_number"], laps["lap_number"])], dtype=bool)
    neutral = neutral_laps(laps, _df(raw, "race_control"))
    laps["neutral"] = laps["lap_number"].isin(neutral)
    after_neutral = laps["lap_number"].isin({n + 1 for n in neutral})
    laps["clean"] = (laps["lap_number"] > 1) & ~laps["neutral"] & ~after_neutral & ~laps["pit_in"] & ~laps["pit_out"] & laps["lap_duration"].notna()
    return laps.sort_values(["driver_number", "lap_number"]).reset_index(drop=True)


def green_windows(laps):
    total = int(laps["lap_number"].max())
    bad = set(laps.loc[laps["neutral"], "lap_number"].unique())
    bad |= {n + 1 for n in bad} | {1}
    out, start = [], None
    for lap in range(1, total + 1):
        if lap in bad:
            if start is not None:
                out.append((start, lap - 1))
                start = None
        elif start is None:
            start = lap
    if start is not None:
        out.append((start, total))
    return out


def phases(laps, focus):
    stops = sorted(set(laps.loc[(laps["driver_number"] == focus) & laps["pit_in"], "lap_number"]))
    out = []
    for a, b in green_windows(laps):
        cuts = [s for s in stops if a <= s <= b]
        edges, cur = [], a
        for s in cuts:
            if s - 1 >= cur:
                edges.append((cur, s - 1))
            cur = s + 2
        if cur <= b:
            edges.append((cur, b))
        out.extend(e for e in edges if e[1] - e[0] + 1 >= MIN_LAPS)
    return out


def _tyre_label(row):
    if row is None or not row.get("compound"):
        return "?"
    c = SHORT.get(row["compound"], row["compound"][:1])
    age = row.get("tyre_age")
    age = 0 if age is None or pd.isna(age) else int(round(age))
    txt = f"{'New' if row.get('new_set') else 'Used'} {c} · {age} lap{'s' if age != 1 else ''} old"
    return txt + " (pitted mid-phase)" if row.get("mixed") else txt


def tyre_state(laps, num, lap):
    r = laps[(laps["driver_number"] == num) & (laps["lap_number"] == lap)]
    if r.empty:
        return None
    r = r.iloc[0]
    return {"compound": r["compound"], "tyre_age": r["tyre_age"], "new_set": r["new_set"]}


def tyre_edge(mine, theirs):
    if not mine or not theirs or not mine.get("compound") or not theirs.get("compound"):
        return ""
    hm, ht = HARDNESS.get(mine["compound"], 9), HARDNESS.get(theirs["compound"], 9)
    am = 0 if pd.isna(mine.get("tyre_age")) else int(mine["tyre_age"])
    at = 0 if pd.isna(theirs.get("tyre_age")) else int(theirs["tyre_age"])
    bits = []
    if ht < hm and max(hm, ht) <= 2:
        bits.append("rival on the softer tyre")
    elif hm < ht and max(hm, ht) <= 2:
        bits.append("you on the softer tyre")
    if at <= am - 3:
        bits.append(f"rival's tyres {am - at} laps fresher")
    elif am <= at - 3:
        bits.append(f"your tyres {at - am} laps fresher")
    return ", ".join(bits) or "even"


def pace(laps, nums, window):
    a, b = window
    w = laps[laps["clean"] & laps["lap_number"].between(a, b) & laps["driver_number"].isin(nums)]
    rows = []
    for n in nums:
        x = w[w["driver_number"] == n]
        if len(x) < MIN_LAPS:
            rows.append({"driver_number": n, "median": np.nan, "best": np.nan, "laps": len(x), "deg": np.nan, "tyre": tyre_state(laps, n, a)})
            continue
        seg = ((x["compound"] != x["compound"].shift()) | (x["tyre_age"].diff().fillna(1) <= 0)).cumsum()
        main = x[seg == seg.value_counts().idxmax()]
        deg = np.polyfit(main["lap_number"], main["lap_duration"], 1)[0] if len(main) >= 4 else np.nan
        tyre = {"compound": main["compound"].iloc[0], "new_set": main["new_set"].iloc[0], "tyre_age": float(main["tyre_age"].mean()),
                "mixed": len(main) < len(x)}
        rows.append({"driver_number": n, "median": float(x["lap_duration"].median()), "best": float(x["lap_duration"].min()),
                     "laps": len(x), "deg": float(deg), "tyre": tyre})
    return pd.DataFrame(rows)


def pace_by_phase(laps, focus, rivals):
    nums = [focus] + [r for r in rivals if r != focus]
    out = []
    for win in phases(laps, focus):
        p = pace(laps, nums, win).set_index("driver_number")
        mine = p.loc[focus] if focus in p.index else None
        for n in nums:
            r = p.loc[n]
            gap = r["median"] - mine["median"] if mine is not None and n != focus else np.nan
            out.append({"phase": f"Laps {win[0]}–{win[1]}", "start": win[0], "end": win[1], "driver_number": n, "median": r["median"], "best": r["best"],
                        "laps": r["laps"], "deg": r["deg"], "tyre": _tyre_label(r["tyre"]), "gap": gap,
                        "edge": "" if n == focus else tyre_edge(mine["tyre"] if mine is not None else None, r["tyre"])})
    return pd.DataFrame(out)


SECTOR_COLS = ["duration_sector_1", "duration_sector_2", "duration_sector_3", "i1_speed", "i2_speed", "st_speed"]


def sectors(laps, nums, window=None):
    w = laps[laps["clean"] & laps["driver_number"].isin(nums)]
    if window:
        w = w[w["lap_number"].between(*window)]
    cols = [c for c in SECTOR_COLS if c in w]
    if w.empty or not cols:
        return pd.DataFrame()
    g = w.groupby("driver_number")[cols].median()
    return g.reindex([n for n in nums if n in g.index])


def race_time(laps):
    x = laps.dropna(subset=["t", "lap_duration"]).copy()
    x["end"] = x["t"] + pd.to_timedelta(x["lap_duration"], unit="s")
    return x.set_index(["driver_number", "lap_number"])["end"]


PEN_RE = re.compile(r"(\d+) SECOND TIME PENALTY FOR CAR (\d+)")


def penalties(raw):
    rc = _df(raw, "race_control")
    if rc.empty:
        return pd.DataFrame(columns=["lap", "driver_number", "seconds", "served", "message"])
    rows = []
    for _, r in rc.iterrows():
        m = PEN_RE.search(str(r.get("message", "")))
        if not m:
            continue
        rows.append({"lap": r.get("lap_number"), "driver_number": int(m.group(2)), "seconds": int(m.group(1)),
                     "served": "PENALTY SERVED" in str(r["message"]), "message": str(r["message"])})
    return pd.DataFrame(rows, columns=["lap", "driver_number", "seconds", "served", "message"])


def moments(raw, num):
    rc = _df(raw, "race_control")
    if rc.empty:
        return []
    tag = re.compile(rf"CARS? (?:\d+ \(\w+\) AND )?{num} \(|CAR {num} \(|AND {num} \(")
    keep = re.compile(r"SAFETY CAR DEPLOYED|VIRTUAL SAFETY CAR DEPLOYED|RED FLAG|STANDING START|CHEQUERED")
    out = []
    for _, r in rc.iterrows():
        msg = str(r.get("message", ""))
        if tag.search(msg) or keep.search(msg):
            if "TRACK LIMITS" in msg and not tag.search(msg):
                continue
            out.append({"lap": None if pd.isna(r.get("lap_number")) else int(r["lap_number"]), "message": msg, "mine": bool(tag.search(msg))})
    return out


def stops(raw, laps, num):
    pits = _df(raw, "pit")
    if pits.empty:
        return []
    pits = pits[pits["driver_number"] == num].sort_values("lap_number")
    allp = _df(raw, "pit")
    green = allp[(allp["pit_duration"] < RED_PIT_S)]
    normal = float(green["pit_duration"].median()) if len(green) else np.nan
    pens = penalties(raw)
    served = pens[(pens["driver_number"] == num) & pens["served"]] if not pens.empty else pens
    neutral = set(laps.loc[laps["neutral"], "lap_number"])
    out, used = [], set()
    for _, p in pits.iterrows():
        lap = int(p["lap_number"])
        before = tyre_state(laps, num, lap)
        after = tyre_state(laps, num, lap + 1) or tyre_state(laps, num, lap + 2)
        dur = p.get("pit_duration")
        red = pd.notna(dur) and dur > RED_PIT_S
        pen = 0
        for i, s in served.iterrows():
            if i not in used and pd.notna(s["lap"]) and lap <= s["lap"] <= lap + 6:
                pen, _ = int(s["seconds"]), used.add(i)
                break
        cond = "Red flag" if red else ("Under Safety Car" if lap in neutral or lap + 1 in neutral else "Green flag")
        extra = None if red or pd.isna(dur) or np.isnan(normal) else float(dur) - normal
        out.append({"lap": lap, "pit_lane": None if red or pd.isna(dur) else float(dur), "condition": cond, "penalty": pen,
                    "extra": extra, "slow": None if extra is None else extra - pen,
                    "from": _tyre_label(before) if before else "?",
                    "to": _tyre_label(after) if after else "?"})
    return out


def stop_cost(laps, num, stop, by_lap_end=None):
    if stop.get("extra") is None or stop["extra"] <= 0.5:
        return []
    ends = by_lap_end if by_lap_end is not None else race_time(laps)
    lap = stop["lap"] + 1
    try:
        mine = ends.loc[(num, lap)]
    except KeyError:
        return []
    at = ends.xs(lap, level="lap_number")
    ahead = at[(at < mine) & (at >= mine - pd.Timedelta(seconds=stop["extra"]))]
    return [(int(n), float((mine - t).total_seconds())) for n, t in ahead.sort_values().items() if n != num]


def strategy(laps, num):
    x = laps[laps["driver_number"] == num].dropna(subset=["compound"])
    if x.empty:
        return []
    out = []
    seg = ((x["compound"] != x["compound"].shift()) | (x["tyre_age"].diff().fillna(1) <= 0)).cumsum()
    for _, g in x.groupby(seg):
        f = g.iloc[0]
        a0 = 0 if pd.isna(f["tyre_age"]) else int(f["tyre_age"])
        out.append({"compound": f["compound"], "short": SHORT.get(f["compound"], "?"), "new": bool(f["new_set"]), "age_start": a0,
                    "start": int(g["lap_number"].min()), "end": int(g["lap_number"].max())})
    return out


def positions(raw, laps):
    pos = _df(raw, "position")
    if pos.empty:
        return pd.DataFrame()
    pos = pos.assign(t=_ts(pos["date"]), driver_number=pos["driver_number"].astype(int)).sort_values("t")
    marks = laps.dropna(subset=["t"])[["driver_number", "lap_number", "t", "lap_duration"]].copy()
    marks["t_end"] = marks["t"] + pd.to_timedelta(marks["lap_duration"].fillna(0), unit="s")
    marks = marks.sort_values("t_end")
    out = pd.merge_asof(marks, pos[["t", "driver_number", "position"]].rename(columns={"t": "t_end"}), on="t_end", by="driver_number", direction="backward")
    return out.pivot_table(index="lap_number", columns="driver_number", values="position", aggfunc="last")


def weekend_sets(weekend_stints, race_session_key, sprint=False):
    if weekend_stints is None or weekend_stints.empty:
        return pd.DataFrame()
    s = weekend_stints.copy()
    s["compound"] = s["compound"].astype(str).str.upper()
    s = s[s["compound"].isin(DRY)]
    age0 = pd.to_numeric(s["tyre_age_at_start"], errors="coerce").fillna(0) == 0
    s = s[age0]
    s["phase"] = np.where(s["session_key"].astype(int) == int(race_session_key), "race", "before")
    alloc = ALLOCATION["sprint" if sprint else "standard"]
    rows = []
    for n, g in s.groupby("driver_number"):
        row = {"driver_number": int(n)}
        for c in DRY:
            before = int(((g["compound"] == c) & (g["phase"] == "before")).sum())
            race = int(((g["compound"] == c) & (g["phase"] == "race")).sum())
            row[f"{c}_before"], row[f"{c}_race"] = before, race
            row[f"{c}_left"] = max(alloc[c] - before, 0)
        rows.append(row)
    return pd.DataFrame(rows).set_index("driver_number")


def default_rivals(raw, laps, focus, n=3):
    res = _df(raw, "session_result")
    order = []
    if not res.empty and "position" in res:
        order = [int(x) for x in res.sort_values("position")["driver_number"]]
    if not order:
        last = laps.sort_values("lap_number").groupby("driver_number")["lap_number"].max().sort_values(ascending=False)
        order = list(last.index)
    team = teams(raw)
    mate = [d for d in team if d != focus and team.get(d) == team.get(focus)]
    picks = []
    if order and order[0] != focus:
        picks.append(order[0])
    picks += [m for m in mate if m not in picks]
    if focus in order:
        i = order.index(focus)
        for j in (i - 1, i + 1):
            if 0 <= j < len(order) and order[j] not in picks and order[j] != focus:
                picks.append(order[j])
    return picks[:n]
