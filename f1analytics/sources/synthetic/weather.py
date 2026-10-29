import numpy as np
import pandas as pd

from f1analytics.columns import WEATHER_COLUMNS, conform

STEP_S = 60


def generate_weather(track, duration_s, rng):
    n = int(duration_s // STEP_S) + 1
    t = np.arange(n) * STEP_S
    lo, hi = track.air_temp_c
    phase = rng.uniform(0, 2 * np.pi)
    air = (lo + hi) / 2 + (hi - lo) / 2 * np.sin(phase + t / 7200 * np.pi) + rng.normal(0, 0.1, n)
    sun = 15 + 10 * (0.5 + 0.5 * np.sin(phase / 2 + t / 5400 * np.pi))
    track_temp = air + sun + rng.normal(0, 0.3, n)
    df = pd.DataFrame({
        "Time": pd.to_timedelta(t, unit="s"),
        "AirTemp": air.round(1),
        "Humidity": np.clip(45 + rng.normal(0, 3, n).cumsum() * 0.2, 20, 95).round(1),
        "Pressure": (track.pressure_hpa + rng.normal(0, 0.3, n)).round(1),
        "Rainfall": np.zeros(n, dtype=bool),
        "TrackTemp": track_temp.round(1),
        "WindDirection": np.mod(rng.uniform(0, 360) + rng.normal(0, 8, n).cumsum(), 360).round(0),
        "WindSpeed": np.clip(1.5 + rng.normal(0, 0.4, n), 0, 8).round(1),
    })
    return conform(df, WEATHER_COLUMNS)
