import numpy as np
import pandas as pd

from f1analytics import config


def seconds(series):
    s = pd.Series(series)
    if pd.api.types.is_timedelta64_dtype(s):
        return s.dt.total_seconds()
    return pd.to_numeric(s, errors="coerce")


def neutralised(track_status):
    status = pd.Series(track_status).fillna("").astype(str)
    return status.apply(lambda s: any(c in s for c in config.NEUTRALISED_STATUS_CODES))


def clean_laps(laps, threshold=1.07):
    df = laps.copy()
    keep = df["LapTime"].notna() & (df["LapNumber"] > 1)
    keep &= df["IsAccurate"].fillna(False).astype(bool)
    keep &= ~df["Deleted"].fillna(False).astype(bool)
    keep &= df["PitInTime"].isna() & df["PitOutTime"].isna()
    keep &= ~neutralised(df["TrackStatus"]).values
    df = df[keep]
    if df.empty:
        return df
    fastest = seconds(df["LapTime"]).min()
    return df[seconds(df["LapTime"]) <= fastest * threshold].copy()


def speed_trap(laps):
    st = (
        laps.dropna(subset=["SpeedST"])
        .groupby(["Driver", "Team"], as_index=False)["SpeedST"].max()
        .sort_values("SpeedST", ascending=False)
        .reset_index(drop=True)
    )
    st.insert(0, "Rank", np.arange(1, len(st) + 1))
    return st


def fastest_lap_per_driver(laps):
    valid = laps[laps["LapTime"].notna()]
    out = valid.loc[valid.groupby("Driver")["LapTime"].idxmin()].copy()
    out["LapTimeSeconds"] = seconds(out["LapTime"])
    out = out.sort_values("LapTimeSeconds").reset_index(drop=True)
    out["GapToFastest"] = out["LapTimeSeconds"] - out["LapTimeSeconds"].iloc[0] if len(out) else []
    return out


def race_gaps(laps, reference):
    t = laps.assign(T=seconds(laps["Time"]))[["Driver", "LapNumber", "T"]].dropna()
    ref = t[t["Driver"] == reference].set_index("LapNumber")["T"]
    t = t[t["LapNumber"].isin(ref.index)].copy()
    t["Gap"] = t["T"] - t["LapNumber"].map(ref)
    return t.pivot(index="LapNumber", columns="Driver", values="Gap").sort_index()


def gap_between(laps, attacker, target, lap):
    t = laps.assign(T=seconds(laps["Time"]))
    a = t[(t["Driver"] == attacker) & (t["LapNumber"] == lap)]["T"]
    b = t[(t["Driver"] == target) & (t["LapNumber"] == lap)]["T"]
    if a.empty or b.empty:
        raise LookupError(f"Lap {lap} missing for {attacker} or {target}")
    return float(a.iloc[0] - b.iloc[0])


def field_gaps_at_lap(laps, driver, lap):
    t = laps.assign(T=seconds(laps["Time"]))
    at = t[t["LapNumber"] == lap]
    me = at[at["Driver"] == driver]["T"]
    if me.empty:
        return []
    gaps = (at["T"] - me.iloc[0])
    return sorted(float(g) for g in gaps if g > 0)


def estimate_pit_loss(laps, default=config.DEFAULT_PIT_LOSS_S):
    df = laps.assign(S=seconds(laps["LapTime"]))
    clean = clean_laps(laps)
    if clean.empty:
        return default
    ref = clean.assign(S=seconds(clean["LapTime"])).groupby("Driver")["S"].median()
    losses = []
    for driver, rows in df.groupby("Driver"):
        if driver not in ref.index:
            continue
        rows = rows.set_index("LapNumber")
        for lap in rows.index[rows["PitInTime"].notna()]:
            nxt = lap + 1
            if nxt not in rows.index or pd.isna(rows.at[nxt, "PitOutTime"]):
                continue
            status = str(rows.at[lap, "TrackStatus"]) + str(rows.at[nxt, "TrackStatus"])
            if any(c in status for c in config.NEUTRALISED_STATUS_CODES):
                continue
            losses.append(rows.at[lap, "S"] + rows.at[nxt, "S"] - 2 * ref[driver])
    return float(np.median(losses)) if losses else default


def lap_time_matrix(laps):
    clean = clean_laps(laps)
    clean = clean.assign(S=seconds(clean["LapTime"]))
    return clean.pivot_table(index="Driver", columns="LapNumber", values="S")
