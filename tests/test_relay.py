import json
import subprocess

from f1analytics.live import relay


def _snap(name="Practice 1", t="2026-11-06T16:00:00+00:00"):
    return {"source": "live", "updated_utc": t, "session": {"name": name, "status": "Finished"},
            "drivers": [{"code": "HAM", "position": 4}], "positions": {"44": [1, 2]}, "car": {"44": {"speed": 300}},
            "feed": {"connected": True, "f1tv": True}}


def test_public_snapshot_drops_f1tv_data():
    out = relay.public_snapshot(_snap())
    assert "positions" not in out and "car" not in out
    assert out["feed"]["relay"] is True and out["feed"]["f1tv"] is False


def test_publish_pushes_single_commit_branch(tmp_path):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    live = tmp_path / "live"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=work, check=True)
    live.mkdir()
    (live / "current.json").write_text(json.dumps(_snap()))
    (live / "laps.json").write_text(json.dumps({"session": "x", "laps": []}))
    c1 = relay.publish(work, live)
    c2 = relay.publish(work, live)
    head = subprocess.run(["git", "rev-parse", "refs/heads/live-feed"], cwd=remote, capture_output=True, text=True).stdout.strip()
    assert head == c2 and c1
    count = subprocess.run(["git", "rev-list", "--count", "live-feed"], cwd=remote, capture_output=True, text=True).stdout.strip()
    assert count == "1"
    pushed = json.loads(subprocess.run(["git", "show", "live-feed:current.json"], cwd=remote, capture_output=True, text=True).stdout)
    assert "car" not in pushed and pushed["drivers"][0]["code"] == "HAM"


def test_parse_refs():
    t = "001e# service=git-upload-pack\n0000015a" + "a" * 40 + " HEAD\x00multi_ack\n003f" + "b" * 40 + " refs/heads/live-feed\n0000"
    assert relay.parse_refs(t) == "b" * 40
    assert relay.parse_refs(t, "main") is None


class _Resp:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


def test_pull_writes_snapshot_with_data_time(tmp_path, monkeypatch):
    snap = relay.public_snapshot(_snap())
    monkeypatch.setattr(relay, "remote_head", lambda *a, **k: "f" * 40)
    monkeypatch.setattr(relay.requests, "get", lambda url, timeout=10: _Resp(snap if url.endswith("current.json") else {"laps": []}))
    sha = relay.pull_once(tmp_path)
    assert sha == "f" * 40
    got = json.loads((tmp_path / "current.json").read_text())
    assert got["feed"]["relay"] is True
    assert abs((tmp_path / "current.json").stat().st_mtime - relay._stamp(snap)) < 1
    assert relay.pull_once(tmp_path, known=sha) == sha


def test_pull_keeps_newer_local_recording(tmp_path, monkeypatch):
    (tmp_path / "current.json").write_text(json.dumps(_snap(t="2026-11-06T18:00:00+00:00")))
    old = relay.public_snapshot(_snap(t="2026-11-06T16:00:00+00:00"))
    monkeypatch.setattr(relay, "remote_head", lambda *a, **k: "e" * 40)
    monkeypatch.setattr(relay.requests, "get", lambda url, timeout=10: _Resp(old))
    relay.pull_once(tmp_path)
    assert json.loads((tmp_path / "current.json").read_text())["updated_utc"].startswith("2026-11-06T18")


def test_fingerprint_ignores_clock_only_changes():
    a = relay.fingerprint(_snap(t="2026-11-06T16:00:00+00:00"))
    b = relay.fingerprint(_snap(t="2026-11-06T16:00:09+00:00"))
    c = relay.fingerprint(_snap(name="Practice 2"))
    assert a == b != c


def test_header_shows_red_flag_when_session_aborted():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_string("""
from f1analytics.ui.pitwall_page import header
header({"session": {"name": "Qualifying", "meeting": "São Paulo Grand Prix", "status": "Aborted",
                    "track_status": "1", "remaining": "00:15:37"}, "feed": {}}, None, "Live feed connected")
""").run(timeout=60)
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "RED FLAG" in text and "GREEN FLAG" not in text


def test_pit_loss_survives_duplicate_lap_rows():
    import pandas as pd
    from f1analytics.pitwall.engine import pit_loss_estimate
    rows = []
    for lap in range(1, 8):
        rows.append({"DriverNumber": "44", "LapNumber": lap, "LapTime": pd.Timedelta(seconds=72), "IsAccurate": True,
                     "PitInTime": pd.Timedelta(seconds=1) if lap == 4 else pd.NaT,
                     "PitOutTime": pd.Timedelta(seconds=2) if lap == 5 else pd.NaT, "TrackStatus": "1"})
    rows.append(dict(rows[4]))
    est, n = pit_loss_estimate(pd.DataFrame(rows), 22.0)
    assert n >= 0
