import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from f1analytics.live.recorder import CURRENT, LIVE_DIR, write_json_atomic

REPO = os.environ.get("F1_RELAY_REPO", "prithvikannan09/f1-pitwall")
BRANCH = os.environ.get("F1_RELAY_BRANCH", "live-feed")
FILES = (CURRENT, "laps.json")
PUSH_EVERY_S = 10.0
PULL_EVERY_S = 8.0
PRIVATE_KEYS = ("positions", "positions_utc", "car")
log = logging.getLogger("f1analytics.relay")


def public_snapshot(snap):
    out = {k: v for k, v in snap.items() if k not in PRIVATE_KEYS}
    out["feed"] = dict(snap.get("feed") or {}, relay=True, f1tv=False)
    return out


def fingerprint(snap):
    import hashlib

    body = {k: v for k, v in public_snapshot(snap).items() if k != "updated_utc"}
    return hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def _git(repo_dir, *args, data=None):
    r = subprocess.run(["git", *args], cwd=repo_dir, input=data, capture_output=True, check=True)
    return r.stdout.decode().strip()


def publish(repo_dir, live_dir=None, remote="origin", branch=BRANCH):
    live_dir = Path(live_dir or LIVE_DIR)
    snap = json.loads((live_dir / CURRENT).read_text())
    blobs = {CURRENT: json.dumps(public_snapshot(snap), default=str).encode()}
    laps = live_dir / "laps.json"
    if laps.exists():
        blobs["laps.json"] = laps.read_bytes()
    entries = []
    for name, data in blobs.items():
        sha = _git(repo_dir, "hash-object", "-w", "--stdin", data=data)
        entries.append(f"100644 blob {sha}\t{name}")
    tree = _git(repo_dir, "mktree", data=("\n".join(entries) + "\n").encode())
    stamp = (snap.get("session") or {}).get("name") or "session"
    commit = _git(repo_dir, "-c", "user.name=pit-wall-relay", "-c", "user.email=relay@localhost",
                  "commit-tree", tree, "-m", f"relay {stamp} {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    _git(repo_dir, "push", "-q", "-f", remote, f"{commit}:refs/heads/{branch}")
    return commit


def run_publisher(repo_dir, live_dir=None, every=PUSH_EVERY_S, stop=lambda: False):
    live_dir = Path(live_dir or LIVE_DIR)
    last, sent = None, None
    while not stop():
        path = live_dir / CURRENT
        try:
            m = path.stat().st_mtime if path.exists() else None
            if m and m != last:
                last = m
                body = fingerprint(json.loads(path.read_text()))
                if body != sent:
                    sha = publish(repo_dir, live_dir)
                    sent = body
                    log.info("relayed %s", sha[:8])
        except Exception as e:
            log.warning("relay push failed: %s", e)
        time.sleep(every)


def parse_refs(text, branch=BRANCH):
    m = re.search(rf"([0-9a-f]{{40}}) refs/heads/{re.escape(branch)}(?=[\x00\n]|$)", text)
    return m.group(1) if m else None


def remote_head(repo=REPO, branch=BRANCH, timeout=10):
    r = requests.get(f"https://github.com/{repo}.git/info/refs", params={"service": "git-upload-pack"}, timeout=timeout,
                     headers={"User-Agent": "git/2.40 f1-pitwall"})
    r.raise_for_status()
    return parse_refs(r.content.decode("latin-1"), branch)


def _stamp(snap):
    t = snap.get("updated_utc")
    try:
        return datetime.fromisoformat(str(t).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def pull_once(live_dir=None, repo=REPO, branch=BRANCH, known=None, timeout=10):
    live_dir = Path(live_dir or LIVE_DIR)
    sha = remote_head(repo, branch, timeout)
    if not sha or sha == known:
        return known
    base = f"https://raw.githubusercontent.com/{repo}/{sha}"
    snap = requests.get(f"{base}/{CURRENT}", timeout=timeout).json()
    when = _stamp(snap) or time.time()
    path = live_dir / CURRENT
    if path.exists():
        try:
            mine = json.loads(path.read_text())
            if not (mine.get("feed") or {}).get("relay") and (_stamp(mine) or 0) > when:
                return sha
        except (json.JSONDecodeError, OSError):
            pass
    try:
        laps = requests.get(f"{base}/laps.json", timeout=timeout).json()
        write_json_atomic(live_dir / "laps.json", laps)
    except Exception:
        pass
    write_json_atomic(path, snap)
    os.utime(path, (when, when))
    return sha


def run_reader(live_dir=None, every=PULL_EVERY_S, stop=lambda: False):
    known = None
    while not stop():
        try:
            known = pull_once(live_dir, known=known)
        except Exception as e:
            log.debug("relay read failed: %s", e)
        time.sleep(every)


def record_with_lock(live_dir=None, raw_log=False, stop=lambda: False):
    import fcntl

    from f1analytics.live.recorder import record

    live_dir = Path(live_dir or LIVE_DIR)
    live_dir.mkdir(parents=True, exist_ok=True)
    lock = open(live_dir / ".recorder.lock", "w")
    while not stop():
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            time.sleep(30)
            continue
        try:
            while not stop():
                try:
                    record(live_dir, raw_log=raw_log, stop=stop)
                except Exception as e:
                    log.warning("recorder stopped: %s", e)
                    time.sleep(10)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def main(repo_dir):
    import threading

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    threading.Thread(target=record_with_lock, name="f1-live-recorder", daemon=True).start()
    log.info("Pit wall relay running: recording F1 live timing and pushing to %s (%s) every %.0fs", REPO, BRANCH, PUSH_EVERY_S)
    run_publisher(repo_dir)
