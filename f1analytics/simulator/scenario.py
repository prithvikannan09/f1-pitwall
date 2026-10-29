from __future__ import annotations

from dataclasses import dataclass, replace

from f1analytics import config
from f1analytics.analysis.laps import estimate_pit_loss, field_gaps_at_lap, gap_between
from f1analytics.analysis.undercut import delta_from_tyres


@dataclass(frozen=True)
class UndercutScenario:
    gap: float = 3.2
    k: int = 1
    pit_loss: float = config.DEFAULT_PIT_LOSS_S
    pit_loss_target: float | None = None
    pit_sigma: float = config.PIT_STOP_SIGMA_S
    slow_stop_prob: float = config.SLOW_STOP_PROB
    slow_stop_extra: float = config.SLOW_STOP_EXTRA_MEAN_S
    fresh_delta: float = 1.4
    deg_old: float = 0.08
    deg_new: float = 0.05
    warmup: float = config.WARMUP_PENALTY_S
    lap_noise: float = config.LAP_NOISE_SIGMA_S
    sc_prob_race: float = config.SC_RACE_PROB
    vsc_prob_race: float = config.VSC_RACE_PROB
    total_laps: int = 71
    sc_pit_factor: float = config.SC_PIT_FACTOR
    vsc_pit_factor: float = config.VSC_PIT_FACTOR
    track_evolution_mean: float = config.TRACK_EVOLUTION_MEAN
    track_evolution_sigma: float = config.TRACK_EVOLUTION_SIGMA
    field_gaps: tuple = config.DEFAULT_FIELD_GAPS
    pass_prob: float = config.PASS_PROB_PER_LAP
    traffic_loss: float = config.TRAFFIC_LOSS_PER_LAP_S
    clear_air: float = config.TRAFFIC_CLEAR_AIR_S
    margin: float = 0.0

    def with_(self, **changes):
        return replace(self, **changes)

    def deterministic(self):
        return replace(
            self, pit_sigma=0.0, slow_stop_prob=0.0, lap_noise=0.0,
            sc_prob_race=0.0, vsc_prob_race=0.0, track_evolution_sigma=0.0, pass_prob=1.0,
        )


def _row(laps, driver, lap):
    hit = laps[(laps["Driver"] == driver) & (laps["LapNumber"] == lap)]
    if hit.empty:
        raise LookupError(f"Lap {lap} missing for {driver}")
    return hit.iloc[0]


def scenario_from_session(sd, attacker, target, lap, deg_models, new_compound=None, sc_probs=None, **overrides):
    laps = sd.laps
    gap = gap_between(laps, attacker, target, lap)
    t_row = _row(laps, target, lap)
    old = t_row["Compound"] if t_row["Compound"] in deg_models else None
    age = float(t_row["TyreLife"]) if t_row["TyreLife"] == t_row["TyreLife"] else 15.0
    if new_compound is None:
        options = [c for c in ("HARD", "MEDIUM", "SOFT") if c in deg_models and c != old]
        new_compound = options[0] if options else old
    fresh, deg_old, deg_new = 1.4, 0.08, 0.05
    if old and new_compound in deg_models:
        a_old, deg_old = deg_models[old]
        a_new, deg_new = deg_models[new_compound]
        fresh = delta_from_tyres(a_old, deg_old, age + 1, a_new, deg_new, 1)
    sc_p, vsc_p = sc_probs or (config.SC_RACE_PROB, config.VSC_RACE_PROB)
    base = UndercutScenario(
        gap=round(gap, 3),
        pit_loss=round(estimate_pit_loss(laps), 2),
        fresh_delta=round(fresh, 3),
        deg_old=round(deg_old, 4),
        deg_new=round(deg_new, 4),
        sc_prob_race=sc_p,
        vsc_prob_race=vsc_p,
        total_laps=int(sd.meta.get("total_laps") or 60),
        field_gaps=tuple(round(g, 2) for g in field_gaps_at_lap(laps, attacker, lap)),
    )
    info = {"target_compound": old, "target_tyre_age": age, "new_compound": new_compound}
    return base.with_(**overrides), info
