import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from f1analytics.analysis.laps import seconds
from f1analytics.sources.openf1_source import _status_windows, _ts, build_laps

RETIRED_AFTER_S = 240


def load_openf1_race(year, gp, source=None):
    from f1analytics.sources.openf1_source import OpenF1Source

    src = source or OpenF1Source()
    event, sess = src._resolve(int(year), gp, "R")
    sk = int(sess["session_key"])
    raw = {ep: src._get(ep, session_key=sk) for ep in ("drivers", "laps", "stints", "pit", "race_control", "weather")}
    raw["session"] = dict(sess)
    raw["event"] = {"EventName": event["EventName"], "Location": event["Location"], "year": int(year)}
    return raw


def load_fixture(folder):
    folder = Path(folder)
    raw = {ep: pd.DataFrame(json.loads((folder / f"{ep}.json").read_text())) for ep in ("drivers", "laps", "stints", "pit", "race_control", "weather")}
    sess = json.loads((folder / "session.json").read_text())
    raw["session"] = sess
    raw["event"] = {"EventName": f"{sess.get('country_name', '')} Grand Prix", "Location": sess.get("circuit_short_name"), "year": int(str(sess.get("date_start", "0000"))[:4])}
    return raw


class RaceReplay:
    def __init__(self, raw):
        self.raw = raw
        self.start = pd.Timestamp(raw["session"]["date_start"]).tz_convert(None) if pd.Timestamp(raw["session"]["date_start"]).tzinfo else pd.Timestamp(raw["session"]["date_start"])
        laps_raw = raw["laps"].copy()
        for col in ("date_start",):
            laps_raw[col] = laps_raw[col].astype(str).replace({"None": None, "NaT": None, "nan": None})
        self.laps = build_laps(laps_raw, raw["drivers"], raw["stints"], raw["pit"], raw["race_control"], self.start)
        self.laps = self.laps.assign(T=seconds(self.laps["Time"]), S=seconds(self.laps["LapTime"]))
        info = raw["drivers"].drop_duplicates("driver_number").set_index(raw["drivers"].drop_duplicates("driver_number")["driver_number"].astype(str))
        self.info = info
        self.total_laps = int(self.laps["LapNumber"].max())
        rc = raw["race_control"].copy()
        rc["t"] = _ts(rc["date"])
        self.rc = rc.sort_values("t")
        wx = raw["weather"].copy()
        if len(wx):
            wx["t"] = _ts(wx["date"])
        self.wx = wx
        self.windows = _status_windows(raw["race_control"])
        lead = self.laps.sort_values("T").groupby("LapNumber")["T"].min()
        self.leader_time = lead

    def status_at(self, abs_time):
        status = "1"
        for t0, t1, code in self.windows:
            if t0 <= abs_time <= t1:
                status = code
        return status

    def snapshot(self, lap):
        lap = int(min(max(lap, 1), self.total_laps))
        upto = self.laps[self.laps["LapNumber"] <= lap]
        if upto.empty:
            return None
        lead_t = float(self.leader_time.get(lap, upto["T"].max()))
        now_abs = self.start + pd.Timedelta(seconds=lead_t)
        last = upto.sort_values("LapNumber").groupby("Driver").tail(1).copy()
        last["retired"] = (last["LapNumber"] < lap) & (last["T"] < lead_t - RETIRED_AFTER_S) & (last["LapNumber"] < self.total_laps)
        lead_at = self.leader_time
        last["gap"] = last["T"] - last["LapNumber"].map(lead_at)
        running = last[~last["retired"]].sort_values(["LapNumber", "T"], ascending=[False, True])
        out = last[last["retired"]].sort_values(["LapNumber", "T"], ascending=[False, True])
        order = pd.concat([running, out])
        drivers = []
        prev = None
        top_laps = int(order["LapNumber"].iloc[0])
        for pos, (_, r) in enumerate(order.iterrows(), start=1):
            num = str(r["DriverNumber"])
            meta = self.info.loc[num] if num in self.info.index else {}
            mine = upto[upto["Driver"] == r["Driver"]]
            stint_rows = mine[mine["Stint"] == r["Stint"]]
            interval = None
            if prev is not None and not r["retired"] and prev["LapNumber"] == r["LapNumber"]:
                interval = float(r["T"] - prev["T"])
            elif prev is not None and not r["retired"]:
                interval = float(r["gap"] - prev["gap"]) if pd.notna(r["gap"]) and pd.notna(prev["gap"]) else None
            drivers.append({
                "number": num,
                "code": r["Driver"],
                "name": meta.get("full_name") if hasattr(meta, "get") else None,
                "team": r["Team"],
                "colour": "#" + str(meta.get("team_colour") or "888888") if hasattr(meta, "get") else "#888888",
                "position": pos,
                "gap_to_leader": 0.0 if pos == 1 else (float(r["gap"]) if pd.notna(r["gap"]) else None),
                "laps_down": int(top_laps - r["LapNumber"]) if not r["retired"] else 0,
                "interval": None if pos == 1 else interval,
                "interval_laps": 0,
                "catching": False,
                "laps": int(r["LapNumber"]),
                "last_lap": float(r["S"]) if pd.notna(r["S"]) else None,
                "best_lap": float(mine["S"].min()) if mine["S"].notna().any() else None,
                "in_pit": bool(pd.notna(r["PitInTime"])),
                "pit_out": bool(pd.notna(r["PitOutTime"])),
                "retired": bool(r["retired"]),
                "stops": int(mine["PitInTime"].notna().sum()),
                "compound": r["Compound"],
                "tyre_age": int(r["TyreLife"]) if pd.notna(r["TyreLife"]) else 0,
                "tyre_new": True,
                "stint": int(r["Stint"]) if pd.notna(r["Stint"]) else 1,
                "compounds_used": sorted({c for c in mine["Compound"].dropna().unique()}),
                "grid": None,
            })
            prev = r
        laps = [
            {
                "number": str(x.DriverNumber), "code": x.Driver, "lap": int(x.LapNumber),
                "lap_time": float(x.S) if pd.notna(x.S) else None,
                "compound": x.Compound, "tyre_age": int(x.TyreLife) if pd.notna(x.TyreLife) else None,
                "stint": int(x.Stint) if pd.notna(x.Stint) else None,
                "pit_in": bool(pd.notna(x.PitInTime)), "pit_out": bool(pd.notna(x.PitOutTime)),
                "track_status": x.TrackStatus,
            }
            for x in upto.itertuples()
        ]
        rc = self.rc[self.rc["t"] <= now_abs].tail(30)
        weather = {}
        if len(self.wx):
            w = self.wx[self.wx["t"] <= now_abs].tail(1)
            if len(w):
                w = w.iloc[0]
                weather = {"AirTemp": w["air_temperature"], "TrackTemp": w["track_temperature"], "Humidity": w["humidity"], "Rainfall": float(w["rainfall"]), "WindSpeed": w["wind_speed"]}
        status = self.status_at(now_abs)
        return {
            "source": "replay",
            "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "session": {
                "meeting": self.raw["event"]["EventName"],
                "circuit": self.raw["event"]["Location"],
                "name": "Race",
                "type": "Race",
                "year": self.raw["event"]["year"],
                "status": "Finished" if lap >= self.total_laps else "Started",
                "lap": lap,
                "total_laps": self.total_laps,
                "track_status": status,
                "track_message": {"1": "AllClear", "4": "SCDeployed", "5": "Red", "6": "VSCDeployed", "7": "VSCEnding"}.get(status, status),
            },
            "weather": weather,
            "drivers": drivers,
            "laps": laps,
            "race_control": [
                {"utc": str(m.date), "lap": m.lap_number if pd.notna(m.lap_number) else None, "category": m.category, "flag": m.flag, "message": m.message}
                for m in rc.itertuples()
            ],
        }
