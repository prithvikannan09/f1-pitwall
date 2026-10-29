from __future__ import annotations

from dataclasses import dataclass, field

from f1analytics import config


@dataclass
class UndercutResult:
    final_gap: float
    success: bool
    breakdown: dict = field(default_factory=dict)
    rejoin_gap: float | None = None
    stuck_in_traffic: bool = False


def fresh_tyre_deltas(fresh_delta, deg_old, deg_new, k):
    return [fresh_delta + (deg_old - deg_new) * (j - 1) for j in range(1, int(k) + 1)]


def delta_from_tyres(alpha_old, beta_old, age_old, alpha_new, beta_new=0.0, age_new=1):
    return (alpha_old + beta_old * age_old) - (alpha_new + beta_new * age_new)


def rejoin_gap(pit_loss, field_gaps):
    ahead = [pit_loss - g for g in field_gaps if pit_loss - g > 0]
    return min(ahead) if ahead else None


def undercut_margin(
    gap,
    pit_loss=config.DEFAULT_PIT_LOSS_S,
    fresh_delta=1.4,
    k=1,
    pit_loss_target=None,
    deg_old=0.08,
    deg_new=0.05,
    warmup=config.WARMUP_PENALTY_S,
    warmup_target=None,
    track_evolution=0.0,
    field_gaps=(),
    pass_prob=config.PASS_PROB_PER_LAP,
    traffic_loss=config.TRAFFIC_LOSS_PER_LAP_S,
    clear_air=config.TRAFFIC_CLEAR_AIR_S,
    margin=0.0,
):
    p_t = pit_loss if pit_loss_target is None else pit_loss_target
    w_t = warmup if warmup_target is None else warmup_target
    w_t_eff = max(0.0, w_t - track_evolution * k)
    deltas = fresh_tyre_deltas(fresh_delta, deg_old, deg_new, k)
    r = rejoin_gap(pit_loss, field_gaps)
    stuck = r is not None and r < clear_air
    traffic = min(k + 1, 1 / pass_prob) * traffic_loss if stuck else 0.0
    terms = {
        "Starting gap": gap,
        "Pit loss difference (you − rival)": pit_loss - p_t,
        "Your out-lap warm-up": warmup,
        "Fresh-tyre gain while rival stays out": -sum(deltas),
        "Rival out-lap (warm-up − your tyre age)": -(w_t_eff - deg_new * k),
        "Traffic after rejoining": traffic,
    }
    final = sum(terms.values())
    return UndercutResult(final, final < margin, terms, r, stuck)
