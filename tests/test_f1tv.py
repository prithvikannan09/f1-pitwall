import base64
import json
import zlib
from pathlib import Path
from unittest import mock

import pytest
from streamlit.testing.v1 import AppTest

from f1analytics.live import signalr
from f1analytics.live.recorder import write_json_atomic
from f1analytics.live.state import LiveState, build_snapshot, decode_z

FIX = Path(__file__).resolve().parent / "fixtures" / "live_state_usgp2026.json"


def _z(obj):
    c = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    return base64.b64encode(c.compress(json.dumps(obj).encode()) + c.flush()).decode()


POS = {"Position": [
    {"Timestamp": "2026-11-01T20:10:00Z", "Entries": {"44": {"Status": "OnTrack", "X": 100, "Y": 200, "Z": 0}, "16": {"Status": "OnTrack", "X": 150, "Y": 260, "Z": 0}}},
    {"Timestamp": "2026-11-01T20:10:00.3Z", "Entries": {"44": {"Status": "OnTrack", "X": 110, "Y": 205, "Z": 0}, "16": {"Status": "OnTrack", "X": 160, "Y": 262, "Z": 0}}},
]}
CAR = {"Entries": [{"Utc": "2026-11-01T20:10:00.3Z", "Cars": {"44": {"Channels": {"0": 11500, "2": 312, "3": 8, "4": 100, "5": 0, "45": 12}}}}]}


def test_decode_z_roundtrip():
    assert decode_z(_z(POS)) == POS


def test_positions_and_car_data_into_snapshot():
    ls = LiveState()
    ls.load_snapshot(dict(json.loads(FIX.read_text()), **{"Position.z": _z(POS)}))
    ls.apply("CarData.z", _z(CAR))
    snap = ls.snapshot()
    assert snap["positions"]["44"] == {"x": 110.0, "y": 205.0, "status": "OnTrack"}
    assert snap["car"]["44"]["speed"] == 312 and snap["car"]["44"]["drs_open"] and snap["car"]["44"]["gear"] == 8
    assert snap["circuit_key"] == 9


def test_bad_payload_is_ignored():
    ls = LiveState()
    ls.load_snapshot(json.loads(FIX.read_text()))
    ls.apply("Position.z", "not-base64!!")
    assert build_snapshot(ls.state, [])["positions"] == {}


class _Neg:
    ok = True
    cookies = {}

    def raise_for_status(self):
        pass

    def json(self):
        return {"connectionToken": "abc"}


def test_signed_in_connect_sends_bearer_and_extra_topics():
    calls = {}

    class WS:
        def send(self, msg):
            calls.setdefault("sent", []).append(msg)

        def recv(self, timeout=None):
            return "{}\x1e"

    def fake_post(url, headers=None, timeout=None):
        calls["neg_headers"] = headers
        return _Neg()

    def fake_connect(url, additional_headers=None, **kw):
        calls["ws_headers"] = additional_headers
        return WS()

    with mock.patch("requests.post", fake_post), mock.patch("websockets.sync.client.connect", fake_connect):
        signalr.connect_once(signalr.TOPICS + signalr.AUTH_TOPICS, access_token="tok123")
    assert calls["neg_headers"]["Authorization"] == "Bearer tok123"
    assert calls["ws_headers"]["Authorization"] == "Bearer tok123"
    assert "Position.z" in calls["sent"][-1] and "CarData.z" in calls["sent"][-1]


def test_no_token_means_free_topics(monkeypatch):
    seen = {}

    def fake_connect_once(topics, access_token=None, timeout=15):
        seen["topics"], seen["token"] = list(topics), access_token
        raise RuntimeError("stop")

    monkeypatch.setattr(signalr, "connect_once", fake_connect_once)
    monkeypatch.setattr(signalr.time, "sleep", lambda s: None)
    gen = signalr.stream(token_fn=lambda: None)
    next(gen)
    assert seen["token"] is None and "Position.z" not in seen["topics"]


def test_pit_wall_shows_gps_map_and_car_data(tmp_path, monkeypatch):
    ls = LiveState()
    ls.load_snapshot(dict(json.loads(FIX.read_text()), **{"Position.z": _z(POS), "CarData.z": _z(CAR)}))
    snap = ls.snapshot()
    snap["feed"] = {"connected": True, "f1tv": True}
    write_json_atomic(tmp_path / "current.json", snap)
    monkeypatch.setenv("F1_LIVE_DIR", str(tmp_path))
    import f1analytics.live.recorder as rec

    monkeypatch.setattr(rec, "LIVE_DIR", tmp_path)
    page = str(Path(__file__).resolve().parent.parent / "pages" / "1_Pit_Wall.py")
    at = AppTest.from_file(page, default_timeout=120)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    heads = [h.value for h in at.subheader]
    assert "Track map (live GPS)" in heads
    text = " ".join(m.value for m in at.markdown)
    assert "312 km/h" in text and "STRAIGHT" in text and "DRS" not in text.split("Car words")[0].split("312 km/h")[1][:400]


def test_public_link_hides_f1tv_data(tmp_path, monkeypatch):
    ls = LiveState()
    ls.load_snapshot(dict(json.loads(FIX.read_text()), **{"Position.z": _z(POS), "CarData.z": _z(CAR)}))
    snap = ls.snapshot()
    write_json_atomic(tmp_path / "current.json", snap)
    import f1analytics.live.recorder as rec

    monkeypatch.setattr(rec, "LIVE_DIR", tmp_path)
    monkeypatch.setenv("PITWALL_KEY", "s3cret-key")
    page = str(Path(__file__).resolve().parent.parent / "pages" / "1_Pit_Wall.py")
    at = AppTest.from_file(page, default_timeout=120)
    at.run()
    assert "Track map (live GPS)" not in [h.value for h in at.subheader]
    at.query_params["key"] = "s3cret-key"
    at.run()
    assert "Track map (live GPS)" not in [h.value for h in at.subheader]
    at.text_input(key="pw_pass").input("wrong")
    at.button(key="FormSubmitter:pw_signin-Sign in").click().run()
    assert at.error and "Track map (live GPS)" not in [h.value for h in at.subheader]
    at.text_input(key="pw_pass").input("s3cret-key")
    at.button(key="FormSubmitter:pw_signin-Sign in").click().run()
    assert not at.exception
    assert "Track map (live GPS)" in [h.value for h in at.subheader]
    assert "s3cret-key" not in " ".join([m.value for m in at.markdown] + [c.value for c in at.caption])


def test_cloud_without_key_hides_f1tv(monkeypatch):
    from f1analytics.ui.pitwall_page import owner_view

    monkeypatch.delenv("PITWALL_KEY", raising=False)
    monkeypatch.setenv("F1_USERNAME", "a")
    monkeypatch.setenv("F1_PASSWORD", "b")
    assert owner_view() is False
    monkeypatch.delenv("F1_USERNAME")
    assert owner_view() is True


def test_own_copy_guide_for_visitors(monkeypatch):
    from pathlib import Path as _P

    monkeypatch.setenv("PITWALL_KEY", "k")
    monkeypatch.setenv("F1_USERNAME", "a")
    monkeypatch.setenv("F1_PASSWORD", "b")
    page = str(_P(__file__).resolve().parent.parent / "pages" / "1_Pit_Wall.py")
    at = AppTest.from_file(page, default_timeout=120)
    at.run()
    assert any("Prefer your own copy" in e.label for e in at.expander)
    assert at.text_input(key="f1tv_email").label == "F1TV email" and at.text_input(key="f1tv_pw").label == "F1TV password"


def test_visitor_f1tv_sign_in_uses_their_own_feed(tmp_path, monkeypatch):
    import time as _t
    from pathlib import Path as _P

    import f1analytics.live.recorder as rec
    import f1analytics.live.userfeed as uf
    import f1analytics.ui.pitwall_page as pw

    ls = LiveState()
    ls.load_snapshot(json.loads(FIX.read_text()))
    write_json_atomic(tmp_path / "current.json", dict(ls.snapshot(), feed={"connected": True}))
    monkeypatch.setattr(rec, "LIVE_DIR", tmp_path)
    monkeypatch.delenv("PITWALL_KEY", raising=False)
    monkeypatch.setenv("F1_USERNAME", "owner")
    monkeypatch.setenv("F1_PASSWORD", "owner-pw")
    seen = {}

    def fake_sign_in(email, password, login_fn=None):
        seen["email"] = email
        if password != "Pa55-visitor-XYZ":
            raise RuntimeError("bad")
        return "tok-visitor", _t.time() + 3600

    tokens = []

    def fake_stream(topics=(), stop=lambda: False, token_fn=None, **kw):
        tokens.append(token_fn())
        yield ("__status__", {"connected": True, "f1tv": True}, None)
        yield ("__snapshot__", {"Position.z": _z(POS), "CarData.z": _z(CAR)}, None)
        while not stop():
            _t.sleep(0.05)

    monkeypatch.setattr(uf, "sign_in", fake_sign_in)
    reg = uf.Registry(stream_fn=fake_stream)
    monkeypatch.setattr(pw, "user_feeds", lambda: reg)
    page = str(_P(__file__).resolve().parent.parent / "pages" / "1_Pit_Wall.py")
    at = AppTest.from_file(page, default_timeout=120)
    at.run()
    assert "Track map (live GPS)" not in [h.value for h in at.subheader]
    at.text_input(key="f1tv_email").input("fan@example.com")
    at.text_input(key="f1tv_pw").input("wrong")
    at.button(key="FormSubmitter:f1tv_signin-Sign in with F1TV").click().run()
    assert at.error and "f1tv_token" not in at.session_state
    at.text_input(key="f1tv_email").input("fan@example.com")
    at.text_input(key="f1tv_pw").input("Pa55-visitor-XYZ")
    at.button(key="FormSubmitter:f1tv_signin-Sign in with F1TV").click().run()
    assert at.session_state["f1tv_token"] == "tok-visitor"
    _t.sleep(0.3)
    at.run()
    assert tokens == ["tok-visitor"]
    assert "Track map (live GPS)" in [h.value for h in at.subheader]
    text = " ".join([m.value for m in at.markdown] + [c.value for c in at.caption])
    assert "Pa55-visitor-XYZ" not in text and "owner-pw" not in text
    assert at.text_input(key="f1tv_pw").value in ("", None) if "f1tv_pw" in at.session_state else True
    at.button(key="pw_signout").click().run()
    assert "f1tv_token" not in at.session_state and not reg.feeds
