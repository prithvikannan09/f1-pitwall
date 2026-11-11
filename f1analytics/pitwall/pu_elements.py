import json
import re
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "styles" / "pu_elements_2026.json"
ELEMENTS = ["ICE", "TC", "EXH", "MGU-K", "ES", "PU-CE", "PU-ANC"]
NAMES = {"ICE": "Engine (ICE)", "TC": "Turbo", "EXH": "Exhaust", "MGU-K": "MGU-K (kinetic motor)", "ES": "Battery (energy store)",
         "PU-CE": "Control electronics", "PU-ANC": "Ancillary parts"}
# 2026 season allowance per driver (Formula1.com guide). No published figure for PU-ANC.
LIMITS = {"ICE": 4, "TC": 4, "EXH": 4, "MGU-K": 3, "ES": 3, "PU-CE": 3}
ROW = re.compile(r"^\s*(\S{1,2})\s+(.+?)\s{2,}(\S.+?)\s{2,}(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$")
DATE = re.compile(r"Date\s+(\d{1,2} \w+ 20\d\d)")
TIME = re.compile(r"Time\s+(\d{1,2}:\d{2})")
TITLE = re.compile(r"(20\d\d [A-ZÀ-Ý\- ]+GRAND PRIX)")


def parse_text(text):
    rows = []
    for line in text.splitlines():
        m = ROW.match(line)
        if m:
            num, team, driver, *vals = m.groups()
            rows.append({"number": int(num) if num.isdigit() else None, "team": team.strip(), "driver": driver.strip(), **{e: int(v) for e, v in zip(ELEMENTS, vals)}})
    title = TITLE.search(text)
    date = DATE.search(text)
    time = TIME.search(text)
    return {"event": title.group(1).title().replace("Grand Prix", "GP") if title else None, "date": date.group(1) if date else None,
            "time": time.group(1) if time else None, "rows": rows}


def load():
    try:
        return json.loads(DATA.read_text())
    except Exception:
        return None


def table(data, i=-1):
    ev = data["events"][i]
    return ev, pd.DataFrame(ev["rows"])


def over_limit(df):
    out = {}
    for _, r in df.iterrows():
        extra = {e: int(r[e]) - LIMITS[e] for e in LIMITS if int(r[e]) > LIMITS[e]}
        if extra:
            out[r["driver"]] = extra
    return out


def history(data, driver):
    rows = []
    for ev in data["events"]:
        hit = next((r for r in ev["rows"] if r["driver"] == driver), None)
        if hit:
            rows.append({"event": ev["label"], **{e: hit[e] for e in ELEMENTS}})
    return pd.DataFrame(rows)


def changes(data, i=-1):
    if len(data["events"]) < 2:
        return pd.DataFrame()
    a = {r["driver"]: r for r in data["events"][i - 1]["rows"]}
    b = data["events"][i]["rows"]
    out = []
    for r in b:
        p = a.get(r["driver"])
        new = {e: r[e] - (p[e] if p else 0) for e in ELEMENTS}
        new = {e: v for e, v in new.items() if v > 0}
        if new:
            out.append({"driver": r["driver"], "team": r["team"], "new": new})
    return pd.DataFrame(out)
