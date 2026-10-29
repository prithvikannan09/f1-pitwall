import time

import numpy as np
import pytest

from f1analytics.analysis.undercut import undercut_margin
from f1analytics.simulator.monte_carlo import per_lap_hazard, simulate, sweep, wilson
from f1analytics.simulator.scenario import UndercutScenario, scenario_from_session


def test_zero_randomness_matches_deterministic():
    sc = UndercutScenario(k=2).deterministic()
    res = simulate(sc, n=200)
    expected = undercut_margin(
        sc.gap, sc.pit_loss, sc.fresh_delta, sc.k, None, sc.deg_old, sc.deg_new, sc.warmup,
        track_evolution=sc.track_evolution_mean, field_gaps=sc.field_gaps, pass_prob=1.0,
    ).final_gap
    assert np.allclose(res.final_gap, expected)


def test_same_seed_same_answer():
    a = simulate(UndercutScenario(), n=2000, seed=7).final_gap
    b = simulate(UndercutScenario(), n=2000, seed=7).final_gap
    assert np.array_equal(a, b)


def test_small_run_agrees_with_large_run():
    sc = UndercutScenario(gap=1.0)
    small = simulate(sc, n=10_000).summary()
    big = simulate(sc, n=100_000, seed=1).summary()
    p = big["success_prob"]
    se = (p * (1 - p) / 10_000) ** 0.5
    assert abs(small["success_prob"] - p) < 4 * se
    assert small["ci_low"] < small["success_prob"] < small["ci_high"]
    assert small["ci_high"] - small["ci_low"] < 0.02


def test_safety_car_hurts_undercut():
    sc = UndercutScenario(gap=1.0, k=2, field_gaps=())
    calm = simulate(sc.with_(sc_prob_race=0.0, vsc_prob_race=0.0)).summary()["success_prob"]
    chaos = simulate(sc.with_(sc_prob_race=1.0, total_laps=1)).summary()["success_prob"]
    assert chaos < calm


def test_success_falls_with_gap():
    curve = sweep(UndercutScenario(), "gap", [0.0, 1.0, 2.0, 3.0, 4.0], n=4000)
    assert curve["success_prob"].is_monotonic_decreasing


def test_hazard_and_wilson():
    assert per_lap_hazard(0.5, 1) == pytest.approx(0.5)
    assert 1 - (1 - per_lap_hazard(0.5, 71)) ** 71 == pytest.approx(0.5)
    lo, hi = wilson(50, 100)
    assert lo < 0.5 < hi


def test_fast_enough():
    start = time.perf_counter()
    simulate(UndercutScenario())
    assert time.perf_counter() - start < 1.0


def test_scenario_from_session(synthetic_race):
    from f1analytics.analysis.degradation import compound_models, fit_stints

    models = compound_models(fit_stints(synthetic_race.laps, 71, True))
    order = synthetic_race.laps.query("LapNumber == 20").sort_values("Position")["Driver"].tolist()
    sc, info = scenario_from_session(synthetic_race, order[1], order[0], 20, models)
    assert sc.gap > 0
    assert 20 < sc.pit_loss < 26
    assert info["new_compound"] in models
