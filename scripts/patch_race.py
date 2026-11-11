import json
import sys
from pathlib import Path

import pandas as pd

from f1analytics.pitwall import racecraft as rc
from f1analytics.sources.openf1_source import OpenF1Source

full = "--full" in sys.argv
gps = "--gps" in sys.argv
args = [a for a in sys.argv[1:] if a not in ("--full", "--gps")]
year, keys = int(args[0]), [int(k) for k in args[1:]]
path = Path(rc.DATA_DIR) / f"racecraft_{year}.json"
data = json.loads(path.read_text())
src = OpenF1Source(timeout=40, retries=4)
CIRCUIT = {11342: "hungaroring", 11353: "zandvoort"}
for sk in keys:
    raw = rc.fetch_race_gps_telemetry(src, sk, rc.jolpica_best_laps(year, CIRCUIT.get(sk, ""))) if gps else (rc.fetch_race_full_telemetry(src, sk) if full else rc.fetch_race(src, sk, telemetry=True))
    import pickle
    pickle.dump(raw, open(f"/tmp/race_{sk}.pkl", "wb"))
    if gps:
        print(sk, "gps point", raw.get("gps_point"), "laps cut for", len(raw["tele_windows"]), "cars:",
              {n: round((b - a).total_seconds(), 2) for n, (a, b) in raw["tele_windows"].items()})
    got = {n: len(v) for n, v in raw["car_data"].items()}
    print(sk, "car_data samples per car:", got)
    rows = rc.race_metrics(raw)
    with_tel = sum(1 for r in rows if r.get("top_speed_kmh") is not None)
    tops = sorted(round(r["top_speed_kmh"], 1) for r in rows if r.get("top_speed_kmh") is not None)
    print(sk, "top speed vs field spread:", tops[:3], "...", tops[-3:])
    print(sk, "rows", len(rows), "with telemetry", with_tel)
    old = [r for r in data["rows"] if int(r["session_key"]) == sk and r.get("top_speed_kmh") is not None]
    if with_tel == 0 or (gps and with_tel < max(len(old), 12)):
        print("not better than what we have (", with_tel, "vs", len(old), "), keeping old rows")
        continue
    data["rows"] = [r for r in data["rows"] if int(r["session_key"]) != sk] + rows
data["profiles"] = rc.build_season(data["rows"])
data["start_tyres"] = rc.start_tyre_stats(data["rows"])
data["built"] = pd.Timestamp.utcnow().isoformat()
path.write_text(json.dumps(data, default=rc._json, indent=1))
print("saved", path)
