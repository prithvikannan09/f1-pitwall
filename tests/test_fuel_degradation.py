import numpy as np
import pandas as pd
import pytest
from scipy import stats

from f1analytics import config
from f1analytics.analysis.degradation import compound_models, fit_stint, fit_stints
from f1analytics.analysis.fuel import fuel_corrected, fuel_gain_per_lap
from f1analytics.sources.synthetic.calendar import COMPOUNDS


def test_fuel_slope_identity():
    laps = pd.DataFrame({"LapNumber": np.arange(10, 30, dtype=float), "LapTime": pd.to_timedelta(np.linspace(80, 81, 20), unit="s")})
    out = fuel_corrected(laps, 71)
    raw = stats.linregress(out["LapNumber"], out["LapTimeSeconds"]).slope
    cor = stats.linregress(out["LapNumber"], out["FuelCorrected"]).slope
    assert cor == pytest.approx(raw + fuel_gain_per_lap(71), abs=1e-9)
    assert fuel_gain_per_lap(71) == pytest.approx(config.FUEL_SEC_PER_KG * config.START_FUEL_KG / 71)


def test_fit_recovers_generator_wear(synthetic_race):
    models = compound_models(fit_stints(synthetic_race.laps, 71, True))
    for comp, (_, beta) in models.items():
        assert abs(beta - COMPOUNDS[comp]["deg"]) < 0.02


def test_short_stints_excluded(synthetic_race):
    stints = fit_stints(synthetic_race.laps, 71, True)
    assert (stints["n"] >= config.DEG_MIN_LAPS).all()
    short = synthetic_race.laps[synthetic_race.laps["LapNumber"] <= 4]
    assert fit_stints(short, 71, True).empty


def test_outlier_trimming():
    life = np.arange(1, 21, dtype=float)
    y = 80 + 0.05 * life
    y[7] += 3.0
    assert abs(fit_stint(life, y)["beta"] - 0.05) < 1e-6
    assert fit_stint(life, y)["n"] == 19
