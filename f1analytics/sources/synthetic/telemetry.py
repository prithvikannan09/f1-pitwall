import numpy as np
import pandas as pd

from f1analytics.columns import TELEMETRY_COLUMNS, conform

G = 9.81
BRAKE_DECEL = 4.5 * G
DRIVE_ACCEL = 1.1 * G
DRS_GAIN = 1.04
ACCEL_HEADROOM = 1.08
SAMPLE_S = 0.25
GEAR_TOP = 8
CORNER_JITTER = 0.03


def speed_profile(track, driver_factor=1.0, drs_allowed=False, ds=1.0, corner_scale=None):
    dist = np.arange(0.0, track.length_m, ds)
    vmax = np.full(dist.size, track.top_speed_kmh / 3.6 * driver_factor)
    if drs_allowed:
        for a, b in track.drs_zones:
            vmax[(dist >= a) & (dist <= b)] *= DRS_GAIN
    limit = vmax.copy()
    scales = corner_scale if corner_scale is not None else np.ones(len(track.corners))
    for (d, apex), scale in zip(track.corners, scales):
        idx = np.abs(dist - d) <= 8
        limit[idx] = np.minimum(limit[idx], apex * scale / 3.6 * driver_factor)
    n = dist.size
    v = limit.copy()
    for _ in range(2):
        for i in range(n - 1, -1, -1):
            nxt = v[(i + 1) % n]
            v[i] = min(v[i], np.sqrt(nxt * nxt + 2 * BRAKE_DECEL * ds))
        for i in range(n):
            prev = v[i - 1]
            acc = max(DRIVE_ACCEL * (1 - prev / (vmax[i] * ACCEL_HEADROOM)), 0.0)
            v[i] = min(v[i], np.sqrt(prev * prev + 2 * acc * ds))
    return dist, v, vmax


def natural_lap_time(track, driver_factor=1.0, drs_allowed=False):
    dist, v, _ = speed_profile(track, driver_factor, drs_allowed)
    return float(np.sum(np.diff(np.append(dist, track.length_m)) / v))


def fit_to_lap_time(v, vmax, seg, lap_time_s):
    slack = np.clip(1 - v / vmax, 0, 1)
    lo, hi = -0.9 / max(slack.max(), 1e-9), 20.0
    lap = lambda c: float(np.sum(seg / (v * (1 + c * slack))))
    if lap(hi) > lap_time_s:
        return v * lap(0) / lap_time_s
    for _ in range(60):
        mid = (lo + hi) / 2
        if lap(mid) > lap_time_s:
            lo = mid
        else:
            hi = mid
    return v * (1 + (lo + hi) / 2 * slack)


def generate_telemetry(track, lap_time_s, driver_factor=1.0, drs_allowed=False, rng=None, start_date=None, session_time=None):
    rng = rng or np.random.default_rng(0)
    corner_scale = 1 + rng.normal(0, CORNER_JITTER, len(track.corners))
    dist, v, vmax = speed_profile(track, driver_factor, drs_allowed, corner_scale=corner_scale)
    seg = np.diff(np.append(dist, track.length_m))
    v = fit_to_lap_time(v, vmax, seg, lap_time_s)
    cum_t = np.concatenate([[0.0], np.cumsum(seg / v)])
    cum_d = np.append(dist, track.length_m)
    t = np.arange(0.0, lap_time_s, SAMPLE_S)
    d = np.interp(t, cum_t, cum_d)
    speed = np.interp(d, dist, v)
    acc = np.gradient(speed, t) if t.size > 1 else np.zeros_like(t)
    vm = np.interp(d, dist, vmax)
    throttle = np.where((acc > 0.3) | (speed > 0.97 * vm), 100.0, np.where(acc < -2.0, 0.0, 40.0))
    throttle = np.clip(throttle + rng.normal(0, 1.0, t.size), 0, 100).round(0)
    brake = acc < -2.0
    frac = np.clip(speed / vm, 0, 1)
    gear = np.clip(np.ceil(frac * GEAR_TOP * 1.05), 1, GEAR_TOP).astype(int)
    band = frac * GEAR_TOP * 1.05 - (gear - 1)
    rpm = (9500 + 2300 * np.clip(band, 0, 1)).round(0)
    drs = np.zeros(t.size, dtype=int)
    if drs_allowed:
        for a, b in track.drs_zones:
            drs[(d >= a) & (d <= b) & ~brake] = 12
    start_date = pd.Timestamp(start_date or "2024-01-01 14:00:00")
    session_time = pd.Timedelta(session_time or 0)
    rel = pd.to_timedelta(t, unit="s")
    df = pd.DataFrame({
        "Date": start_date + session_time + rel,
        "SessionTime": session_time + rel,
        "Time": rel,
        "RPM": rpm,
        "Speed": (speed * 3.6).round(1),
        "nGear": gear,
        "Throttle": throttle,
        "Brake": brake,
        "DRS": drs,
        "Distance": d,
    })
    return conform(df, TELEMETRY_COLUMNS)
