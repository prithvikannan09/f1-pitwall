import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from f1analytics import config
from f1analytics.live.state import LiveState

LIVE_DIR = Path(os.environ.get("F1_LIVE_DIR", config.ROOT / "data" / "live"))
CURRENT = "current.json"
WRITE_EVERY_S = 2.0
log = logging.getLogger("f1analytics.live")


def write_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, default=str))
    os.replace(tmp, path)


def read_current(live_dir=None):
    path = Path(live_dir or LIVE_DIR) / CURRENT
    if not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None, None
    age = time.time() - path.stat().st_mtime
    return data, age


def session_key(state):
    info = state.get("SessionInfo") or {}
    return f"{(info.get('Meeting') or {}).get('Name')}|{info.get('Name')}|{info.get('StartDate')}"


def record(live_dir=None, stream=None, stop=lambda: False, raw_log=True):
    from f1analytics.live.signalr import stream as live_stream

    live_dir = Path(live_dir or LIVE_DIR)
    live_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    raw = open(live_dir / f"raw_{stamp}.jsonl", "a") if raw_log else None
    ls = LiveState()
    status = {"connected": False}
    last_write = 0.0
    try:
        for topic, data, ts in (stream or live_stream(stop=stop)):
            if raw:
                raw.write(json.dumps({"t": time.time(), "topic": topic, "data": data, "ts": ts}) + "\n")
            if topic == "__status__":
                status = data
                log.info("feed status: %s", data)
                write_json_atomic(live_dir / "feed.json", dict(data, at=time.time()))
            elif topic == "__snapshot__":
                key = session_key(data)
                laps_file = live_dir / "laps.json"
                saved = json.loads(laps_file.read_text()) if laps_file.exists() else {}
                ls.load_snapshot(data)
                if saved.get("session") == key and not ls.laps:
                    ls.laps = saved.get("laps", [])
                log.info("snapshot: %s, %d laps restored", key, len(ls.laps))
            else:
                ls.apply(topic, data)
            now = time.monotonic()
            if now - last_write > WRITE_EVERY_S and ls.state:
                snap = ls.snapshot("live")
                snap["feed"] = status
                write_json_atomic(live_dir / CURRENT, snap)
                write_json_atomic(live_dir / "laps.json", {"session": session_key(ls.state), "laps": ls.laps})
                last_write = now
            if stop():
                break
    finally:
        if raw:
            raw.close()
        if ls.state:
            snap = ls.snapshot("live")
            snap["feed"] = status
            write_json_atomic(live_dir / CURRENT, snap)
    return ls


def read_feed(live_dir=None):
    path = Path(live_dir or LIVE_DIR) / "feed.json"
    try:
        data = json.loads(path.read_text())
        return data, time.time() - float(data.get("at", 0))
    except Exception:
        return None, None


def replay_raw(path):
    ls = LiveState()
    with open(path) as fh:
        for line in fh:
            rec = json.loads(line)
            if rec["topic"] == "__snapshot__":
                ls.load_snapshot(rec["data"])
            elif rec["topic"] != "__status__":
                ls.apply(rec["topic"], rec["data"])
    return ls
