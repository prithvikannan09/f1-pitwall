import base64
import copy
import json
import re
import zlib
from datetime import datetime, timezone

NEUTRAL = {"4", "5", "6", "7"}
GAP_LAPS = re.compile(r"^\+?\s*(\d+)\s*L", re.I)


DRS_OPEN = {10, 12, 14}


def decode_z(data):
    if isinstance(data, (dict, list)):
        return data
    raw = zlib.decompress(base64.b64decode(data), -zlib.MAX_WBITS)
    return json.loads(raw)


def latest_positions(payload):
    frames = (payload or {}).get("Position") or []
    if not frames:
        return None, {}
    frame = frames[-1]
    out = {}
    for num, e in (frame.get("Entries") or {}).items():
        try:
            out[str(num)] = {"x": float(e["X"]), "y": float(e["Y"]), "status": e.get("Status")}
        except (KeyError, TypeError, ValueError):
            continue
    return frame.get("Timestamp"), out


def latest_car_data(payload):
    entries = (payload or {}).get("Entries") or []
    if not entries:
        return None, {}
    entry = entries[-1]
    out = {}
    for num, car in (entry.get("Cars") or {}).items():
        ch = (car or {}).get("Channels") or {}
        try:
            drs = int(ch.get("45", 0) or 0)
            out[str(num)] = {
                "rpm": int(ch.get("0", 0) or 0), "speed": int(ch.get("2", 0) or 0), "gear": int(ch.get("3", 0) or 0),
                "throttle": int(ch.get("4", 0) or 0), "brake": int(ch.get("5", 0) or 0) > 0,
                "drs": drs, "drs_open": drs in DRS_OPEN,
            }
        except (TypeError, ValueError):
            continue
    return entry.get("Utc"), out


def merge(dst, src):
    if isinstance(src, dict):
        if isinstance(dst, list) and all(str(k).isdigit() for k in src if k != "_kf"):
            for k, v in src.items():
                if k == "_kf":
                    continue
                i = int(k)
                while len(dst) <= i:
                    dst.append({})
                dst[i] = merge(dst[i], v)
            return dst
        if not isinstance(dst, dict):
            dst = {}
        for k, v in src.items():
            if k == "_deleted":
                for gone in v or []:
                    dst.pop(str(gone), None)
                continue
            dst[k] = merge(dst.get(k), v)
        return dst
    return copy.deepcopy(src)


def parse_time(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        if ":" in s:
            m, rest = s.split(":", 1)
            return int(m) * 60 + float(rest)
        return float(s)
    except ValueError:
        return None


def parse_gap(value):
    if value is None:
        return None, 0
    s = str(value).strip()
    if not s:
        return None, 0
    if s.upper().startswith("LAP"):
        return 0.0, 0
    m = GAP_LAPS.match(s)
    if m:
        return None, int(m.group(1))
    try:
        return float(s.lstrip("+")), 0
    except ValueError:
        return None, 0


def _speeds(line):
    sp = line.get("Speeds") or {}
    out = {}
    for key in ("ST", "I1", "I2", "FL"):
        out[key.lower()] = _f((sp.get(key) or {}).get("Value"))
    return out


def _f(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class LiveState:
    def __init__(self):
        self.state = {}
        self.laps = []
        self._count = {}
        self._flags = {}
        self._status_seen = set()

    def load_snapshot(self, data):
        data = dict(data or {})
        compressed = {k: data.pop(k) for k in list(data) if k.endswith(".z")}
        self.state = merge({}, data)
        for topic, payload in compressed.items():
            if payload:
                self._apply_z(topic, payload)
        for num, line in self._lines().items():
            self._count[num] = int(line.get("NumberOfLaps") or 0)
            self._flags[num] = self._pit_flags(line)

    def _lines(self):
        return {k: v for k, v in ((self.state.get("TimingData") or {}).get("Lines") or {}).items() if isinstance(v, dict)}

    @staticmethod
    def _pit_flags(line):
        flags = set()
        if line.get("InPit"):
            flags.add("pit_in")
        if line.get("PitOut"):
            flags.add("pit_out")
        return flags

    def _apply_z(self, topic, payload):
        try:
            decoded = decode_z(payload)
        except Exception:
            return
        if topic == "Position.z":
            ts, pos = latest_positions(decoded)
            if pos:
                self.state["_positions"] = {"utc": ts, "cars": {**(self.state.get("_positions") or {}).get("cars", {}), **pos}}
        elif topic == "CarData.z":
            ts, car = latest_car_data(decoded)
            if car:
                self.state["_car"] = {"utc": ts, "cars": {**(self.state.get("_car") or {}).get("cars", {}), **car}}

    def apply(self, topic, delta):
        if topic.endswith(".z"):
            self._apply_z(topic, delta)
            return
        if topic == "TrackStatus":
            self.state = merge(self.state, {topic: delta})
            status = str((self.state.get("TrackStatus") or {}).get("Status", "1"))
            for flags in self._flags.values():
                flags.add(f"status:{status}")
            return
        if topic != "TimingData":
            self.state = merge(self.state, {topic: delta})
            return
        self.state = merge(self.state, {topic: delta})
        lines = (delta or {}).get("Lines") or {}
        for num, upd in lines.items():
            if not isinstance(upd, dict):
                continue
            line = self._lines().get(num, {})
            flags = self._flags.setdefault(num, set())
            if upd.get("InPit"):
                flags.add("pit_in")
            if upd.get("PitOut"):
                flags.add("pit_out")
            new = upd.get("NumberOfLaps")
            if new is not None and int(new) > self._count.get(num, 0):
                self._record(num, int(new), line, flags)
                self._count[num] = int(new)
                self._flags[num] = {"pit_out"} if (line.get("InPit") or line.get("PitOut")) else set()
                self._flags[num].add(f"status:{self._track_status()}")
            elif "LastLapTime" in upd and isinstance(upd["LastLapTime"], dict) and upd["LastLapTime"].get("Value"):
                self._fix_last(num, line)

    def _track_status(self):
        return str((self.state.get("TrackStatus") or {}).get("Status", "1"))

    def _stint(self, num):
        app = ((self.state.get("TimingAppData") or {}).get("Lines") or {}).get(num) or {}
        stints = app.get("Stints") or []
        if isinstance(stints, dict):
            stints = [stints[k] for k in sorted(stints, key=int)]
        stints = [s for s in stints if isinstance(s, dict)]
        return stints

    def _record(self, num, lap, line, flags):
        stints = self._stint(num)
        cur = stints[-1] if stints else {}
        statuses = {f.split(":", 1)[1] for f in flags if f.startswith("status:")}
        statuses.add(self._track_status())
        status = "".join(sorted(statuses - {"1"})) or "1"
        self.laps.append({
            "number": num,
            "lap": lap,
            "lap_time": parse_time((line.get("LastLapTime") or {}).get("Value")),
            "compound": cur.get("Compound"),
            "tyre_age": int(cur.get("TotalLaps") or 0) or None,
            "stint": len(stints) or None,
            "pit_in": "pit_in" in flags or bool(line.get("InPit")),
            "pit_out": "pit_out" in flags,
            "track_status": status,
            **_speeds(line),
        })

    def _fix_last(self, num, line):
        for rec in reversed(self.laps):
            if rec["number"] == num:
                if rec["lap"] == self._count.get(num):
                    rec["lap_time"] = parse_time((line.get("LastLapTime") or {}).get("Value"))
                return

    def snapshot(self, source="live"):
        return build_snapshot(self.state, self.laps, source)


STATIC = "https://livetiming.formula1.com/static/"
RADIO_KEEP = 60


def radio_clips(state, codes):
    info = state.get("SessionInfo") or {}
    base = STATIC + str(info.get("Path") or "")
    caps = (state.get("TeamRadio") or {}).get("Captures") or []
    if isinstance(caps, dict):
        caps = [caps[k] for k in sorted(caps, key=lambda k: int(k) if str(k).isdigit() else 0)]
    out = []
    for c in caps:
        if not isinstance(c, dict) or not c.get("Path"):
            continue
        num = str(c.get("RacingNumber") or "")
        out.append({"utc": c.get("Utc"), "number": num, "code": codes.get(num, num), "url": base + c["Path"]})
    out.sort(key=lambda c: c["utc"] or "", reverse=True)
    return out[:RADIO_KEEP]


def build_snapshot(state, laps, source="live"):
    info = state.get("SessionInfo") or {}
    meeting = info.get("Meeting") or {}
    count = state.get("LapCount") or {}
    track = state.get("TrackStatus") or {}
    wx = state.get("WeatherData") or {}
    dlist = {k: v for k, v in (state.get("DriverList") or {}).items() if isinstance(v, dict)}
    timing = {k: v for k, v in ((state.get("TimingData") or {}).get("Lines") or {}).items() if isinstance(v, dict)}
    app = (state.get("TimingAppData") or {}).get("Lines") or {}
    drivers = []
    for num in sorted(set(dlist) | set(timing), key=lambda n: int(n) if str(n).isdigit() else 999):
        d, t = dlist.get(num, {}), timing.get(num, {})
        stints = (app.get(num) or {}).get("Stints") or []
        if isinstance(stints, dict):
            stints = [stints[k] for k in sorted(stints, key=int)]
        stints = [s for s in stints if isinstance(s, dict)]
        cur = stints[-1] if stints else {}
        gap, gap_laps = parse_gap(t.get("GapToLeader"))
        interval, int_laps = parse_gap((t.get("IntervalToPositionAhead") or {}).get("Value"))
        pos = t.get("Position") or t.get("Line")
        drivers.append({
            "number": str(num),
            "code": d.get("Tla") or str(num),
            "name": d.get("FullName") or d.get("BroadcastName"),
            "team": d.get("TeamName"),
            "colour": "#" + (d.get("TeamColour") or "888888"),
            "position": int(pos) if str(pos or "").isdigit() else None,
            "gap_to_leader": gap,
            "laps_down": gap_laps,
            "interval": interval,
            "interval_laps": int_laps,
            "catching": bool((t.get("IntervalToPositionAhead") or {}).get("Catching")),
            "laps": int(t.get("NumberOfLaps") or 0),
            "last_lap": parse_time((t.get("LastLapTime") or {}).get("Value")),
            "best_lap": parse_time((t.get("BestLapTime") or {}).get("Value")),
            "in_pit": bool(t.get("InPit")),
            "pit_out": bool(t.get("PitOut")),
            "retired": bool(t.get("Retired")) or bool(t.get("Stopped")),
            "stops": int(t.get("NumberOfPitStops") or 0),
            "compound": cur.get("Compound"),
            "tyre_age": int(cur.get("TotalLaps") or 0),
            "tyre_new": str(cur.get("New", "")).lower() == "true",
            "stint": len(stints),
            "compounds_used": sorted({s.get("Compound") for s in stints if s.get("Compound")}),
            "grid": d.get("GridPos") or (app.get(num) or {}).get("GridPos"),
        })
    for x in drivers:
        if x["position"] == 1 and x["gap_to_leader"] is None:
            x["gap_to_leader"] = 0.0
    codes = {x["number"]: x["code"] for x in drivers}
    messages = (state.get("RaceControlMessages") or {}).get("Messages") or []
    if isinstance(messages, dict):
        messages = [messages[k] for k in sorted(messages, key=int)]
    start = info.get("StartDate") or ""
    clock = state.get("ExtrapolatedClock") or {}
    return {
        "source": source,
        "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": {
            "meeting": meeting.get("Name"),
            "circuit": (meeting.get("Circuit") or {}).get("ShortName") or meeting.get("Location"),
            "name": info.get("Name"),
            "type": info.get("Type"),
            "year": int(start[:4]) if start[:4].isdigit() else None,
            "status": (state.get("SessionStatus") or {}).get("Status"),
            "lap": int(count.get("CurrentLap") or 0),
            "total_laps": int(count.get("TotalLaps") or 0),
            "track_status": str(track.get("Status", "1")),
            "track_message": track.get("Message"),
            "remaining": clock.get("Remaining"),
        },
        "weather": {k: _f(v) for k, v in wx.items() if not k.startswith("_")},
        "drivers": drivers,
        "laps": [dict(r, code=codes.get(r["number"], r["number"])) for r in laps],
        "race_control": [
            {"utc": m.get("Utc"), "lap": m.get("Lap"), "category": m.get("Category"), "flag": m.get("Flag"), "message": m.get("Message")}
            for m in messages[-30:] if isinstance(m, dict)
        ],
        "radio": radio_clips(state, codes),
        "circuit_key": (meeting.get("Circuit") or {}).get("Key"),
        "positions": (state.get("_positions") or {}).get("cars") or {},
        "positions_utc": (state.get("_positions") or {}).get("utc"),
        "car": (state.get("_car") or {}).get("cars") or {},
    }
