import numpy as np
import pandas as pd
from scipy import stats

from f1analytics.analysis.fuel import fuel_corrected
from f1analytics.analysis.laps import clean_laps, seconds


def weather_trend(weather, window=5):
    if weather.empty:
        return weather.copy()
    df = weather.copy()
    df["Minutes"] = seconds(df["Time"]) / 60
    for col in ("AirTemp", "TrackTemp", "Humidity", "WindSpeed"):
        df[f"{col}Smooth"] = df[col].rolling(window, min_periods=1, center=True).mean()
    return df


def attach_weather(laps, weather):
    if weather.empty:
        return laps.assign(TrackTemp=np.nan, AirTemp=np.nan)
    left = laps.assign(_t=seconds(laps["LapStartTime"])).dropna(subset=["_t"]).sort_values("_t")
    right = weather.assign(_t=seconds(weather["Time"]))[["_t", "TrackTemp", "AirTemp"]].sort_values("_t")
    return pd.merge_asof(left, right, on="_t", direction="nearest").drop(columns="_t")


def pace_vs_track_temp(laps, weather, total_laps, is_race):
    clean = clean_laps(laps)
    if clean.empty or weather.empty:
        return pd.DataFrame(), None
    if is_race:
        clean = fuel_corrected(clean, total_laps)
        y = "FuelCorrected"
    else:
        clean = clean.assign(LapTimeSeconds=seconds(clean["LapTime"]))
        y = "LapTimeSeconds"
    clean = clean.assign(Residual=clean[y] - clean.groupby(["Driver", "Stint"])[y].transform("median"))
    merged = attach_weather(clean, weather).dropna(subset=["TrackTemp", "Residual"])
    if merged["TrackTemp"].nunique() < 3:
        return merged, None
    fit = stats.linregress(merged["TrackTemp"], merged["Residual"])
    return merged, {"slope_s_per_c": fit.slope, "intercept": fit.intercept, "r2": fit.rvalue ** 2, "n": len(merged)}
