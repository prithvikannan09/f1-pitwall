import pytest

from f1analytics.analysis.pit_window import best_per_strategy, one_stop_optimum, optimise, stint_time

MODELS = {"SOFT": (80.0, 0.09), "MEDIUM": (80.35, 0.06), "HARD": (80.7, 0.04)}


def test_stint_time_formula():
    assert stint_time(80.0, 0.1, 3, 1) == pytest.approx(80.1 + 80.2 + 80.3)


def test_brute_force_matches_closed_form():
    plans = optimise(71, 22.0, MODELS, max_stops=1)
    best = plans[plans["compounds"] == "MEDIUM-HARD"].iloc[0]
    exact = one_stop_optimum(*MODELS["MEDIUM"], *MODELS["HARD"], 71)
    assert abs(best["pit_laps"][0] - exact) <= 1


def test_two_compound_rule():
    plans = optimise(71, 22.0, MODELS)
    assert all(len(set(c.split("-"))) >= 2 for c in plans["compounds"])


def test_min_stint_enforced():
    plans = optimise(71, 22.0, MODELS, min_stint=10)
    for laps in plans["pit_laps"]:
        edges = [0, *laps, 71]
        assert min(b - a for a, b in zip(edges, edges[1:])) >= 10


def test_bigger_pit_loss_means_fewer_stops():
    models = {"SOFT": (80.0, 0.12), "HARD": (80.7, 0.06)}
    cheap = best_per_strategy(optimise(71, 5.0, models)).iloc[0]["stops"]
    dear = best_per_strategy(optimise(71, 40.0, models)).iloc[0]["stops"]
    assert cheap == 2 and dear == 1


def test_start_compound_filter():
    plans = optimise(71, 22.0, MODELS, start_compound="SOFT")
    assert plans["compounds"].str.startswith("SOFT").all()
