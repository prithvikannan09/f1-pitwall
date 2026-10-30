import logging
import threading
import time

from f1analytics.live.state import LiveState

log = logging.getLogger("f1analytics.live")
MAX_FEEDS = 6
IDLE_S = 180


class UserFeed:
    """One visitor's own F1TV connection: car positions and car data only, with their token."""

    def __init__(self, token, stream_fn=None):
        self._token = token
        self.state = LiveState()
        self.status = {"connected": False}
        self.seen = time.time()
        self._stop = False
        self._stream_fn = stream_fn
        self.thread = threading.Thread(target=self._run, name="f1tv-user-feed", daemon=True)
        self.thread.start()

    def _run(self):
        from f1analytics.live.signalr import stream

        fn = self._stream_fn or stream
        try:
            for topic, data, _ in fn(topics=[], stop=lambda: self._stop, token_fn=lambda: self._token):
                if self._stop:
                    break
                if topic == "__status__":
                    self.status = data
                elif topic == "__snapshot__":
                    self.state.load_snapshot({k: v for k, v in (data or {}).items() if k in ("Position.z", "CarData.z")})
                elif topic in ("Position.z", "CarData.z"):
                    self.state.apply(topic, data)
        except Exception as exc:
            log.warning("user feed stopped: %s", type(exc).__name__)
            self.status = {"connected": False, "error": "stopped"}

    def stop(self):
        self._stop = True
        self._token = None

    def touch(self):
        self.seen = time.time()

    def data(self):
        pos = self.state.state.get("_positions") or {}
        car = self.state.state.get("_car") or {}
        return {"positions": pos.get("cars") or {}, "positions_utc": pos.get("utc"), "car": car.get("cars") or {},
                "f1tv": bool(self.status.get("f1tv")), "connected": bool(self.status.get("connected"))}


class Registry:
    def __init__(self, max_feeds=MAX_FEEDS, idle_s=IDLE_S, stream_fn=None):
        self.stream_fn = stream_fn
        self.feeds = {}
        self.lock = threading.Lock()
        self.max_feeds = max_feeds
        self.idle_s = idle_s

    def sweep(self):
        now = time.time()
        with self.lock:
            for sid in [s for s, f in self.feeds.items() if now - f.seen > self.idle_s]:
                self.feeds.pop(sid).stop()

    def get(self, sid, token, stream_fn=None):
        self.sweep()
        with self.lock:
            feed = self.feeds.get(sid)
            if feed is not None:
                feed.touch()
                return feed
            if len(self.feeds) >= self.max_feeds:
                return None
            feed = self.feeds[sid] = UserFeed(token, stream_fn=stream_fn or self.stream_fn)
            return feed

    def drop(self, sid):
        with self.lock:
            feed = self.feeds.pop(sid, None)
        if feed:
            feed.stop()


def sign_in(email, password, login_fn=None):
    """Sign in to F1 once and return (token_value, expires_at). The password is not kept anywhere."""
    if login_fn is None:
        from fastf1.internals.f1account.login import login as login_fn
    token = login_fn(str(email).strip(), password)
    if not token.is_valid():
        raise ValueError("expired token")
    return token.value, float(token.expires_at)
