import json
import logging
import ssl
import time
from urllib.parse import quote

HOST = "livetiming.formula1.com/signalrcore"
RS = "\x1e"
TOPICS = [
    "Heartbeat", "SessionInfo", "SessionStatus", "TrackStatus", "LapCount", "DriverList",
    "TimingData", "TimingAppData", "TimingStats", "RaceControlMessages", "WeatherData", "ExtrapolatedClock",
    "TeamRadio",
]
AUTH_TOPICS = ["Position.z", "CarData.z"]
PING_EVERY_S = 10
log = logging.getLogger("f1analytics.live")


def _ssl_context():
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def decode(raw):
    for part in raw.split(RS):
        if part.strip():
            yield json.loads(part)


def connect_once(topics=TOPICS, timeout=15, access_token=None):
    import requests
    from websockets.sync.client import connect

    auth = {"Authorization": f"Bearer {access_token}"} if access_token else {}
    neg = requests.post(f"https://{HOST}/negotiate?negotiateVersion=1", headers=auth, timeout=timeout)
    neg.raise_for_status()
    token = neg.json()["connectionToken"]
    cookie = "; ".join(f"{k}={v}" for k, v in neg.cookies.items())
    headers = dict(auth)
    if cookie:
        headers["Cookie"] = cookie
    ws = connect(
        f"wss://{HOST}?id={quote(token)}",
        additional_headers=headers or None,
        ssl=_ssl_context(),
        open_timeout=timeout,
        max_size=2 ** 26,
    )
    ws.send(json.dumps({"protocol": "json", "version": 1}) + RS)
    ws.recv(timeout=timeout)
    ws.send(json.dumps({"type": 1, "target": "Subscribe", "arguments": [list(topics)], "invocationId": "0"}) + RS)
    return ws


def stream(topics=TOPICS, stop=lambda: False, max_backoff=30, token_fn=None):
    from websockets.exceptions import ConnectionClosed

    if token_fn is None:
        from f1analytics.live.auth import subscription_token as token_fn
    backoff = 1
    while not stop():
        access = None
        try:
            access = token_fn()
        except Exception as exc:
            log.warning("token lookup failed: %s", exc)
        wanted = list(topics) + ([t for t in AUTH_TOPICS if t not in topics] if access else [])
        try:
            try:
                ws = connect_once(wanted, access_token=access)
            except Exception as exc:
                if not access:
                    raise
                log.warning("signed-in connect failed (%s); using free data", exc)
                access = None
                ws = connect_once(topics)
        except Exception as exc:
            log.warning("connect failed: %s (retrying in %ss)", exc, backoff)
            yield ("__status__", {"connected": False, "error": str(exc)}, None)
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
            continue
        backoff = 1
        yield ("__status__", {"connected": True, "f1tv": bool(access)}, None)
        last_ping = time.monotonic()
        try:
            while not stop():
                if time.monotonic() - last_ping > PING_EVERY_S:
                    ws.send(json.dumps({"type": 6}) + RS)
                    last_ping = time.monotonic()
                try:
                    raw = ws.recv(timeout=1)
                except TimeoutError:
                    continue
                for msg in decode(raw):
                    kind = msg.get("type")
                    if kind == 3 and msg.get("invocationId") == "0":
                        yield ("__snapshot__", msg.get("result") or {}, None)
                    elif kind == 1 and msg.get("target") == "feed":
                        args = msg.get("arguments") or []
                        if len(args) >= 2:
                            yield (args[0], args[1], args[2] if len(args) > 2 else None)
                    elif kind == 7:
                        raise ConnectionClosed(None, None)
        except (ConnectionClosed, OSError) as exc:
            log.warning("connection dropped: %s", exc)
            yield ("__status__", {"connected": False, "error": "connection dropped"}, None)
        finally:
            try:
                ws.close()
            except Exception:
                pass
