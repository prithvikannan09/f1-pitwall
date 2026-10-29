import numpy as np
import pandas as pd
from scipy import stats

from f1analytics import config
from f1analytics.analysis.fuel import fuel_corrected
from f1analytics.analysis.laps import clean_laps, seconds

DRY = ("SOFT", "MEDIUM", "HARD")
STINT_COLUMNS = ["Driver", "Team", "Stint", "Compound", "n", "alpha", "beta", "stderr", "r2", "first_life", "last_life", "fuel_corrected"]


def _fit(x, y):
    res = stats.linregress(x, y)
    return res.intercept, res.slope, res.stderr, res.rvalue ** 2


def fit_stint(tyre_life, lap_seconds, mad_cutoff=config.DEG_MAD_CUTOFF):
    x = np.asarray(tyre_life, dtype=float)
    y = np.asarray(lap_seconds, dtype=float)
    alpha, beta, _, _ = _fit(x, y)
    resid = y - (alpha + beta * x)
    mad = 1.4826 * np.median(np.abs(resid - np.median(resid)))
    if mad > 0:
        keep = np.abs(resid) <= mad_cutoff * mad
        if keep.sum() >= 3:
            x, y = x[keep], y[keep]
    alpha, beta, se, r2 = _fit(x, y)
    return {"alpha": alpha, "beta": beta, "stderr": se, "r2": r2, "n": int(x.size)}


def fit_stints(laps, total_laps, is_race, min_laps=config.DEG_MIN_LAPS, start_fuel_kg=config.START_FUEL_KG, sec_per_kg=config.FUEL_SEC_PER_KG):
    clean = clean_laps(laps)
    if clean.empty:
        return pd.DataFrame(columns=STINT_COLUMNS)
    if is_race:
        clean = fuel_corrected(clean, total_laps, start_fuel_kg, sec_per_kg)
        y_col = "FuelCorrected"
    else:
        clean = clean.assign(LapTimeSeconds=seconds(clean["LapTime"]))
        y_col = "LapTimeSeconds"
    rows = []
    for (driver, stint), g in clean.groupby(["Driver", "Stint"]):
        g = g.dropna(subset=["TyreLife", y_col])
        if len(g) < min_laps or g["TyreLife"].nunique() < 3:
            continue
        fit = fit_stint(g["TyreLife"], g[y_col])
        if fit["n"] < min_laps:
            continue
        rows.append({
            "Driver": driver, "Team": g["Team"].iloc[0], "Stint": stint,
            "Compound": g["Compound"].iloc[0], **fit,
            "first_life": g["TyreLife"].min(), "last_life": g["TyreLife"].max(),
            "fuel_corrected": bool(is_race),
        })
    return pd.DataFrame(rows, columns=STINT_COLUMNS)


def compound_models(stints, compounds=DRY):
    models = {}
    for comp, g in stints.groupby("Compound"):
        if comp in compounds and len(g):
            models[comp] = (float(g["alpha"].median()), float(g["beta"].median()))
    return models


def predicted_curve(alpha, beta, max_life):
    life = np.arange(1, int(max_life) + 1)
    return pd.DataFrame({"TyreLife": life, "Predicted": alpha + beta * life})
