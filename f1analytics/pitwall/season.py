from datetime import datetime, timezone

import pandas as pd
import requests

JOLPICA = "https://api.jolpi.ca/ergast/f1"
OPENF1 = "https://api.openf1.org/v1"
SESSION_KEYS = (("FirstPractice", "Practice 1"), ("SecondPractice", "Practice 2"), ("ThirdPractice", "Practice 3"),
                ("SprintQualifying", "Sprint Qualifying"), ("Sprint", "Sprint"), ("Qualifying", "Qualifying"))
FLAGS = {
    "Australia": "🇦🇺", "China": "🇨🇳", "Japan": "🇯🇵", "Bahrain": "🇧🇭", "Saudi Arabia": "🇸🇦", "USA": "🇺🇸", "United States": "🇺🇸",
    "Canada": "🇨🇦", "Monaco": "🇲🇨", "Spain": "🇪🇸", "Austria": "🇦🇹", "UK": "🇬🇧", "United Kingdom": "🇬🇧", "Belgium": "🇧🇪",
    "Hungary": "🇭🇺", "Netherlands": "🇳🇱", "Italy": "🇮🇹", "Azerbaijan": "🇦🇿", "Singapore": "🇸🇬", "Mexico": "🇲🇽",
    "Brazil": "🇧🇷", "Qatar": "🇶🇦", "UAE": "🇦🇪", "United Arab Emirates": "🇦🇪", "Malaysia": "🇲🇾", "Portugal": "🇵🇹",
}


def _get(path, timeout=15, **params):
    out, offset = [], 0
    while True:
        r = requests.get(f"{JOLPICA}/{path}.json", params=dict(params, limit=100, offset=offset), timeout=timeout)
        r.raise_for_status()
        d = r.json()["MRData"]
        out.append(d)
        total, got = int(d.get("total") or 0), int(d.get("limit") or 100)
        offset += got
        if offset >= total:
            return out


def _when(block):
    if not block or not block.get("date"):
        return None
    return pd.Timestamp(f"{block['date']}T{(block.get('time') or '00:00:00Z').replace('Z', '')}", tz="UTC")


def schedule(year):
    races = []
    for page in _get(f"{year}"):
        races += page["RaceTable"]["Races"]
    rows = []
    for r in races:
        loc = r["Circuit"]["Location"]
        sessions = [(name, _when(r.get(k))) for k, name in SESSION_KEYS if r.get(k)]
        sessions.append(("Race", _when(r)))
        rows.append({"round": int(r["round"]), "name": r["raceName"], "country": loc.get("country"), "locality": loc.get("locality"),
                     "circuit": r["Circuit"]["circuitName"], "circuit_id": r["Circuit"]["circuitId"], "race_utc": _when(r),
                     "sessions": sessions, "flag": FLAGS.get(loc.get("country"), "🏁"), "sprint": bool(r.get("Sprint"))})
    return rows


def results(year):
    rows = []
    for page in _get(f"{year}/results"):
        for race in page["RaceTable"]["Races"]:
            for x in race.get("Results", []):
                d, c = x["Driver"], x["Constructor"]
                rows.append({"round": int(race["round"]), "race": race["raceName"], "code": d.get("code") or d["familyName"][:3].upper(),
                             "driver": f"{d['givenName']} {d['familyName']}", "family": d["familyName"], "team": c["name"],
                             "grid": int(x.get("grid") or 0), "position": int(x["position"]), "text": x.get("positionText"),
                             "points": float(x.get("points") or 0), "status": x.get("status"),
                             "fastest": (x.get("FastestLap") or {}).get("rank") == "1"})
    return pd.DataFrame(rows)


def driver_standings(year, rnd=None):
    path = f"{year}/{rnd}/driverstandings" if rnd else f"{year}/driverstandings"
    lists = _get(path)[0]["StandingsTable"]["StandingsLists"]
    if not lists:
        return pd.DataFrame(), None
    L = lists[0]
    rows = [{"pos": int(x["position"]) if x.get("position") else 99, "code": x["Driver"].get("code") or x["Driver"]["familyName"][:3].upper(),
             "driver": f"{x['Driver']['givenName']} {x['Driver']['familyName']}", "family": x["Driver"]["familyName"],
             "team": (x.get("Constructors") or [{}])[-1].get("name"), "points": float(x["points"]), "wins": int(x["wins"])}
            for x in L["DriverStandings"]]
    return pd.DataFrame(rows), int(L["round"])


def constructor_standings(year, rnd=None):
    path = f"{year}/{rnd}/constructorstandings" if rnd else f"{year}/constructorstandings"
    lists = _get(path)[0]["StandingsTable"]["StandingsLists"]
    if not lists:
        return pd.DataFrame(), None
    L = lists[0]
    rows = [{"pos": int(x["position"]) if x.get("position") else 99, "team": x["Constructor"]["name"], "points": float(x["points"]),
             "wins": int(x["wins"])} for x in L["ConstructorStandings"]]
    return pd.DataFrame(rows), int(L["round"])


def with_change(now, before, key):
    if now.empty:
        return now
    now = now.copy()
    now["gap"] = now["points"] - now["points"].max()
    if before is None or before.empty:
        now["change"] = 0
        return now
    prev = dict(zip(before[key], before["pos"]))
    now["change"] = [int(prev[k] - p) if k in prev else 0 for k, p in zip(now[key], now["pos"])]
    return now


def next_race(sched, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    for r in sched:
        if r["race_utc"] is not None and r["race_utc"] + pd.Timedelta(hours=3) > now:
            return r
    return None


def progress(sched, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    done = sum(1 for r in sched if r["race_utc"] is not None and r["race_utc"] + pd.Timedelta(hours=3) <= now)
    return done, len(sched)


def driver_card(res, standings, code):
    if standings.empty or code not in set(standings["code"]):
        return None
    row = standings[standings["code"] == code].iloc[0]
    mine = res[res["code"] == code].sort_values("round") if not res.empty else res
    ahead = standings[standings["pos"] == row["pos"] - 1]
    return {
        "pos": int(row["pos"]), "points": row["points"], "wins": int(row["wins"]), "driver": row["driver"], "team": row["team"],
        "gap_leader": float(row["points"] - standings["points"].max()),
        "gap_ahead": float(row["points"] - ahead["points"].iloc[0]) if len(ahead) else None,
        "ahead": ahead["code"].iloc[0] if len(ahead) else None,
        "podiums": int((mine["position"] <= 3).sum()) if len(mine) else 0,
        "last5": [(int(r["round"]), r["text"]) for _, r in mine.tail(5).iterrows()] if len(mine) else [],
        "dnfs": int((~mine["text"].astype(str).str.isdigit()).sum()) if len(mine) else 0,
    }


def records(res, standings=None):
    if res.empty:
        return []
    out = []
    last = int(res["round"].max())
    lr = res[res["round"] == last].sort_values("position")
    if len(lr):
        w = lr.iloc[0]
        out.append(("Race", f"{w['driver']} won the {w['race']}", f"Round {last}"))
        climb = lr.assign(gain=lr["grid"].where(lr["grid"] > 0, 22) - lr["position"]).sort_values("gain", ascending=False).iloc[0]
        if climb["gain"] >= 5:
            out.append(("Race", f"{climb['driver']} gained {int(climb['gain'])} places in {climb['race']} (P{int(climb['grid']) or 'L'} → P{int(climb['position'])})", f"Round {last}"))
    wins = res[res["position"] == 1].groupby(["code", "driver"]).size().sort_values(ascending=False)
    if len(wins):
        (code, name), n = wins.index[0], int(wins.iloc[0])
        out.append(("Driver", f"{name} leads the season with {n} wins", f"{len(wins)} different winners this year"))
    pods = res[res["position"] <= 3].groupby("driver").size().sort_values(ascending=False)
    if len(pods):
        out.append(("Driver", f"{pods.index[0]} has the most podiums: {int(pods.iloc[0])}", "Top three finishes"))
    team_wins = res[res["position"] == 1].groupby("team").size().sort_values(ascending=False)
    if len(team_wins):
        out.append(("Team", f"{team_wins.index[0]} have won {int(team_wins.iloc[0])} of {last} races", "Most wins by a team"))
    finished = res.assign(fin=res["text"].astype(str).str.isdigit())
    streak = []
    for code, g in finished.sort_values("round").groupby("code"):
        n = 0
        for f in reversed(g["fin"].tolist()):
            if not f:
                break
            n += 1
        streak.append((n, g["driver"].iloc[0]))
    if streak:
        n, name = max(streak)
        out.append(("Driver", f"{name} has finished {n} races in a row", "Longest run without a DNF right now"))
    pts = res[res["points"] > 0].groupby("driver").size().sort_values(ascending=False)
    if len(pts):
        out.append(("Driver", f"{pts.index[0]} has scored points in {int(pts.iloc[0])} of {last} races", "Most points finishes"))
    fl = res[res["fastest"]].groupby("driver").size().sort_values(ascending=False)
    if len(fl):
        out.append(("Driver", f"{fl.index[0]} has the most fastest laps: {int(fl.iloc[0])}", "Fastest lap of the race"))
    return out
