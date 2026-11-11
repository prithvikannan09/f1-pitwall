import json
import sys
from pathlib import Path

import pandas as pd

from f1analytics.pitwall import racecraft as rc
from f1analytics.sources.openf1_source import OpenF1Source

full = "--full" in sys.argv
args = [a for a in sys.argv[1:] if a != "--full"]
year, keys = int(args[0]), [int(k) for k in args[1:]]
path = Path(rc.DATA_DIR) / f"racecraft_{year}.json"
data = json.loads(path.read_text())
src = OpenF1Source(timeout=40, retries=4)
for sk in keys:
    raw = rc.fetch_race_full_telemetry(src, sk) if full else rc.fetch_race(src, sk, telemetry=True)
    got = {n: len(v) for n, v in raw["car_data"].items()}
    print(sk, "car_data samples per car:", got)
    rows = rc.race_metrics(raw)
    with_tel = sum(1 for r in rows if r.get("top_speed_kmh") is not None)
    tops = sorted(round(r["top_speed_kmh"], 1) for r in rows if r.get("top_speed_kmh") is not None)
    print(sk, "top speed vs field spread:", tops[:3], "...", tops[-3:])
    print(sk, "rows", len(rows), "with telemetry", with_tel)
    if with_tel == 0:
        print("still no telemetry, keeping old rows")
        continue
    data["rows"] = [r for r in data["rows"] if int(r["session_key"]) != sk] + rows
data["profiles"] = rc.build_season(data["rows"])
data["start_tyres"] = rc.start_tyre_stats(data["rows"])
data["built"] = pd.Timestamp.utcnow().isoformat()
path.write_text(json.dumps(data, default=rc._json, indent=1))
print("saved", path)
