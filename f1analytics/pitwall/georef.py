"""Place OpenF1 track coordinates on the real map.

OpenF1 positions are in the circuit's own x/y frame, not GPS. We fit a similarity transform (scale, rotation, optional mirror,
shift) between a lap's x/y outline and the circuit's real outline from the MIT-licensed bacinger/f1-circuits GeoJSON."""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

GEO = Path(__file__).resolve().parent.parent / "styles" / "circuits_geo.geojson"
ALIASES = {"monte carlo": "monaco", "montréal": "montreal", "spa-francorchamps": "spa francorchamps", "são paulo": "sao paulo",
           "marina bay": "singapore", "kuala lumpur": "sepang", "miami gardens": "miami", "yas island": "yas marina"}
N = 400
R_EARTH = 6371000.0


@lru_cache(maxsize=1)
def _features():
    return json.loads(GEO.read_text())["features"]


def outline(location):
    key = str(location or "").strip().lower()
    key = ALIASES.get(key, key)
    for f in _features():
        if str(f["properties"].get("Location", "")).lower() == key:
            g = f["geometry"]
            pts = g["coordinates"] if g["type"] == "LineString" else g["coordinates"][0]
            return np.asarray(pts, dtype=float)
    return None


def to_local(lonlat, origin):
    lon0, lat0 = origin
    x = np.radians(lonlat[:, 0] - lon0) * R_EARTH * np.cos(np.radians(lat0))
    y = np.radians(lonlat[:, 1] - lat0) * R_EARTH
    return np.column_stack([x, y])


def to_lonlat(xy, origin):
    lon0, lat0 = origin
    lon = lon0 + np.degrees(xy[:, 0] / (R_EARTH * np.cos(np.radians(lat0))))
    lat = lat0 + np.degrees(xy[:, 1] / R_EARTH)
    return np.column_stack([lon, lat])


def resample(pts, n=N):
    pts = np.asarray(pts, dtype=float)
    if np.hypot(*(pts[0] - pts[-1])) > 1e-9:
        pts = np.vstack([pts, pts[:1]])
    seg = np.hypot(*np.diff(pts, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, s[-1], n, endpoint=False)
    return np.column_stack([np.interp(t, s, pts[:, 0]), np.interp(t, s, pts[:, 1])])


def _umeyama(src, dst):
    ms, md = src.mean(0), dst.mean(0)
    a, b = src - ms, dst - md
    u, sig, vt = np.linalg.svd(b.T @ a / len(src))
    d = np.sign(np.linalg.det(u @ vt))
    D = np.diag([1, d])
    R = u @ D @ vt
    scale = (sig * np.diag(D)).sum() / (a ** 2).sum() * len(src)
    t = md - scale * R @ ms
    return scale, R, t


def fit(track_xy, location):
    """Return a transform dict mapping OpenF1 x/y to lon/lat, plus the fit error in metres."""
    geo = outline(location)
    if geo is None or len(track_xy) < 20:
        return None
    origin = (float(geo[:, 0].mean()), float(geo[:, 1].mean()))
    dst = resample(to_local(geo, origin))
    src0 = resample(np.asarray(track_xy, dtype=float))
    best = None
    for mirror in (1.0, -1.0):
        for rev in (False, True):
            s = src0 * np.array([1.0, mirror])
            s = s[::-1] if rev else s
            for k in range(0, N, 2):
                ss = np.roll(s, -k, axis=0)
                scale, R, t = _umeyama(ss, dst)
                err = float(np.sqrt(((scale * ss @ R.T + t - dst) ** 2).sum(1).mean()))
                if best is None or err < best[0]:
                    best = (err, mirror, scale, R, t)
    err, mirror, scale, R, t = best
    return {"origin": origin, "mirror": mirror, "scale": float(scale), "R": R.tolist(), "t": t.tolist(), "rms_m": err}


def apply(tf, xy):
    xy = np.asarray(xy, dtype=float) * np.array([1.0, tf["mirror"]])
    local = tf["scale"] * xy @ np.asarray(tf["R"]).T + np.asarray(tf["t"])
    return to_lonlat(local, tf["origin"])
