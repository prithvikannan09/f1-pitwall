import numpy as np
import pandas as pd

from f1analytics.analysis.laps import seconds


def distance_delta(tel_a, tel_b, step_m=5.0):
    da = tel_a["Distance"].to_numpy(float)
    db = tel_b["Distance"].to_numpy(float)
    ta = seconds(tel_a["Time"]).to_numpy(float)
    tb = seconds(tel_b["Time"]).to_numpy(float)
    end = min(da.max(), db.max())
    grid = np.arange(0.0, end, step_m)
    ia, ib = np.argsort(da), np.argsort(db)
    t_a = np.interp(grid, da[ia], ta[ia])
    t_b = np.interp(grid, db[ib], tb[ib])
    return pd.DataFrame({
        "Distance": grid,
        "Delta": t_b - t_a,
        "SpeedA": np.interp(grid, da[ia], tel_a["Speed"].to_numpy(float)[ia]),
        "SpeedB": np.interp(grid, db[ib], tel_b["Speed"].to_numpy(float)[ib]),
    })


def braking_points(tel, min_drop_kmh=40):
    df = tel.reset_index(drop=True)
    start = df["Brake"].astype(bool) & ~df["Brake"].astype(bool).shift(1, fill_value=False)
    rows = []
    for i in df.index[start]:
        seg = df.loc[i:]
        end = seg.index[~seg["Brake"].astype(bool)]
        j = end[0] if len(end) else df.index[-1]
        drop = df.at[i, "Speed"] - df.loc[i:j, "Speed"].min()
        if drop >= min_drop_kmh:
            rows.append({"Distance": float(df.at[i, "Distance"]), "EntrySpeed": float(df.at[i, "Speed"]), "MinSpeed": float(df.loc[i:j, "Speed"].min())})
    return pd.DataFrame(rows, columns=["Distance", "EntrySpeed", "MinSpeed"])


def lap_summary(tel):
    return {
        "top_speed": float(tel["Speed"].max()),
        "min_speed": float(tel["Speed"].min()),
        "full_throttle_pct": float((tel["Throttle"] >= 98).mean() * 100),
        "braking_pct": float(tel["Brake"].astype(bool).mean() * 100),
    }
