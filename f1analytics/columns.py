import numpy as np
import pandas as pd

TD = "timedelta64[ns]"

LAP_COLUMNS = {
    "Time": TD,
    "Driver": "object",
    "DriverNumber": "object",
    "Team": "object",
    "LapTime": TD,
    "LapNumber": "float64",
    "Stint": "float64",
    "PitOutTime": TD,
    "PitInTime": TD,
    "Sector1Time": TD,
    "Sector2Time": TD,
    "Sector3Time": TD,
    "SpeedST": "float64",
    "Compound": "object",
    "TyreLife": "float64",
    "LapStartTime": TD,
    "TrackStatus": "object",
    "Position": "float64",
    "Deleted": "object",
    "IsAccurate": "bool",
}

TELEMETRY_COLUMNS = {
    "Date": "datetime64[ns]",
    "SessionTime": TD,
    "Time": TD,
    "RPM": "float64",
    "Speed": "float64",
    "nGear": "int64",
    "Throttle": "float64",
    "Brake": "bool",
    "DRS": "int64",
    "Distance": "float64",
}

WEATHER_COLUMNS = {
    "Time": TD,
    "AirTemp": "float64",
    "Humidity": "float64",
    "Pressure": "float64",
    "Rainfall": "bool",
    "TrackTemp": "float64",
    "WindDirection": "float64",
    "WindSpeed": "float64",
}


def _empty(dtype, n):
    if dtype == TD:
        return pd.Series(pd.NaT, index=range(n), dtype=TD)
    if dtype.startswith("datetime"):
        return pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns]")
    if dtype == "bool":
        return pd.Series(False, index=range(n))
    if dtype == "object":
        return pd.Series([None] * n, dtype="object")
    return pd.Series(np.nan, index=range(n), dtype="float64")


def conform(df, spec):
    out = pd.DataFrame(df).copy().reset_index(drop=True)
    n = len(out)
    for col, dtype in spec.items():
        if col not in out.columns:
            out[col] = _empty(dtype, n)
            continue
        try:
            if dtype == TD:
                out[col] = pd.to_timedelta(out[col])
            elif dtype.startswith("datetime"):
                out[col] = pd.to_datetime(out[col])
            elif dtype == "bool":
                out[col] = out[col].fillna(False).astype(bool)
            elif dtype == "int64":
                out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype("int64")
            elif dtype == "float64":
                out[col] = pd.to_numeric(out[col], errors="coerce").astype("float64")
            else:
                out[col] = out[col].astype("object")
        except (TypeError, ValueError):
            pass
    extra = [c for c in out.columns if c not in spec]
    return out[list(spec) + extra]
