"""Fill race pace for a race whose OpenF1 lap feed is incomplete, using Jolpica (Ergast) lap times.
Usage: python scripts/patch_pace_jolpica.py YEAR SESSION_KEY ROUND"""
import json
import sys
from pathlib import Path

import pandas as pd

from f1analytics import config
from f1analytics.pitwall import racecraft as rc
from f1analytics.pitwall.season import _get


def secs(t):
    m, s = (t.split(":") + ["0"])[:2] if ":" in t else ("0", t)
    return int(m) * 60 + float(s)


def pace_from_jolpica(year, rnd):
    res = _get(f"{year}/{rnd}/results")[0]["RaceTable"]["Races"][0]["Results"]
    code = {r["Driver"]["driverId"]: r["Driver"].get("code") for r in res}
    rows = []
    for page in _get(f"{year}/{rnd}/laps"):
        for race in page["RaceTable"]["Races"]:
            for lap in race["Laps"]:
                for t in lap["Timings"]:
                    rows.append({"code": code.get(t["driverId"]), "lap": int(lap["number"]), "dur": secs(t["time"])})
    laps = pd.DataFrame(rows).dropna(subset=["code"])
    pits = set()
    for page in _get(f"{year}/{rnd}/pitstops"):
        for race in page["RaceTable"]["Races"]:
            for p in race.get("PitStops", []):
                pits |= {(code.get(p["driverId"]), int(p["lap"])), (code.get(p["driverId"]), int(p["lap"]) + 1)}
    total = int(laps["lap"].max())
    fuel = config.FUEL_SEC_PER_KG * config.START_FUEL_KG / total
    laps["corr"] = laps["dur"] - fuel * (total - laps["lap"])
    ok = (laps["lap"] > 1) & ~pd.Series([(c, l) in pits for c, l in zip(laps["code"], laps["lap"])], index=laps.index)
    field = laps[ok].groupby("lap")["dur"].median()
    ok &= laps["dur"] < laps["lap"].map(field) * 1.07
    med = laps[ok].groupby("code")["dur"].transform("median")
    clean = laps[ok][laps[ok]["dur"] < med * 1.07]
    pace = clean.groupby("code")["corr"].median()
    best = pace.min()
    return {c: {"pace_pct": float((p - best) / best * 100), "clean_laps": int((clean["code"] == c).sum())} for c, p in pace.items()}


if __name__ == "__main__":
    year, sk, rnd = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    path = Path(rc.DATA_DIR) / f"racecraft_{year}.json"
    data = json.loads(path.read_text())
    got = pace_from_jolpica(year, rnd)
    n = 0
    for r in data["rows"]:
        if int(r["session_key"]) == sk and r["code"] in got:
            r.update(got[r["code"]])
            n += 1
    data["profiles"] = rc.build_season(data["rows"])
    path.write_text(json.dumps(data, default=rc._json, indent=1))
    print("updated", n, "drivers;", sorted(((round(v["pace_pct"], 2), c, v["clean_laps"]) for c, v in got.items()))[:6])
