import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from f1analytics import config


@dataclass
class SimResult:
    scenario: object
    final_gap: np.ndarray
    flags: dict

    @property
    def gain(self):
        return self.scenario.gap - self.final_gap

    @property
    def success(self):
        return self.final_gap < self.scenario.margin

    def summary(self):
        n = self.final_gap.size
        k = int(self.success.sum())
        lo, hi = wilson(k, n)
        fail = ~self.success
        causes = {name: float(arr[fail].mean()) if fail.any() else 0.0 for name, arr in self.flags.items()}
        g = self.gain
        return {
            "runs": n,
            "success_prob": k / n,
            "ci_low": lo,
            "ci_high": hi,
            "gain_mean": float(g.mean()),
            "gain_p5": float(np.percentile(g, 5)),
            "gain_p50": float(np.percentile(g, 50)),
            "gain_p95": float(np.percentile(g, 95)),
            "final_gap_mean": float(self.final_gap.mean()),
            "failure_causes": causes,
        }


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def per_lap_hazard(p_race, total_laps):
    p_race = min(max(p_race, 0.0), 1.0)
    if p_race >= 1.0:
        return 1.0
    return 1 - (1 - p_race) ** (1 / max(int(total_laps), 1))


def _stops(rng, n, mean, sigma, slow_prob, slow_extra):
    stop = mean + rng.normal(0.0, 1.0, n) * sigma
    slow = rng.random(n) < slow_prob
    extra = rng.exponential(1.0, n) * slow_extra
    return stop + np.where(slow, extra, 0.0), slow


def simulate(sc, n=config.SIM_RUNS, seed=config.SIM_SEED):
    rng = np.random.default_rng(seed)
    k = int(sc.k)
    p_t_mean = sc.pit_loss if sc.pit_loss_target is None else sc.pit_loss_target
    p_a, slow_a = _stops(rng, n, sc.pit_loss, sc.pit_sigma, sc.slow_stop_prob, sc.slow_stop_extra)
    p_t, slow_t = _stops(rng, n, p_t_mean, sc.pit_sigma, sc.slow_stop_prob, sc.slow_stop_extra)
    h_sc = per_lap_hazard(sc.sc_prob_race, sc.total_laps)
    h_vsc = per_lap_hazard(sc.vsc_prob_race, sc.total_laps)
    u_sc = rng.random((n, k))
    u_vsc = rng.random((n, k))
    sc_hit = u_sc < h_sc
    vsc_hit = u_vsc < h_vsc
    first_sc = np.where(sc_hit.any(1), sc_hit.argmax(1) + 1, k + 1)
    first_vsc = np.where(vsc_hit.any(1), vsc_hit.argmax(1) + 1, k + 1)
    is_sc = (first_sc <= k) & (first_sc <= first_vsc)
    is_vsc = (first_vsc <= k) & ~is_sc
    first = np.where(is_sc, first_sc, np.where(is_vsc, first_vsc, k + 1))
    factor = np.where(is_sc, sc.sc_pit_factor, np.where(is_vsc, sc.vsc_pit_factor, 1.0))
    p_t = p_t * factor
    j = np.arange(1, k + 1)
    deltas = sc.fresh_delta + (sc.deg_old - sc.deg_new) * (j - 1)
    counted = j[None, :] < first[:, None]
    tyre_gain = (deltas[None, :] * counted).sum(1)
    noise = rng.normal(0.0, 1.0, (n, k + 1)).sum(1) * sc.lap_noise * math.sqrt(2)
    tau = sc.track_evolution_mean + rng.normal(0.0, 1.0, n) * sc.track_evolution_sigma
    w_t = np.maximum(0.0, sc.warmup - tau * k)
    gaps = np.asarray(sc.field_gaps, dtype=float)
    if gaps.size:
        diff = p_a[:, None] - gaps[None, :]
        ahead = np.where(diff > 0, diff, np.inf).min(1)
        stuck = ahead < sc.clear_air
    else:
        stuck = np.zeros(n, dtype=bool)
    stuck_laps = np.minimum(rng.geometric(min(max(sc.pass_prob, 1e-6), 1.0), n), k + 1)
    traffic = np.where(stuck, stuck_laps * sc.traffic_loss, 0.0)
    final = sc.gap + (p_a - p_t) + sc.warmup - tyre_gain - (w_t - sc.deg_new * k) + traffic + noise
    flags = {
        "Safety Car": is_sc,
        "Virtual Safety Car": is_vsc,
        "Traffic after rejoin": stuck,
        "Slow pit stop (you)": slow_a,
    }
    return SimResult(sc, final, flags)


def sweep(sc, field, values, n=5000, seed=config.SIM_SEED):
    rows = []
    for v in values:
        s = simulate(sc.with_(**{field: v}), n=n, seed=seed).summary()
        rows.append({field: v, "success_prob": s["success_prob"], "ci_low": s["ci_low"], "ci_high": s["ci_high"], "gain_mean": s["gain_mean"]})
    return pd.DataFrame(rows)


def sc_probability_from_history(con, location):
    q = """
        SELECT
            COUNT(DISTINCT s.session_id) AS races,
            COUNT(DISTINCT CASE WHEN l.track_status LIKE '%4%' THEN s.session_id END) AS sc_races,
            COUNT(DISTINCT CASE WHEN l.track_status LIKE '%6%' THEN s.session_id END) AS vsc_races
        FROM sessions s JOIN laps l ON l.session_id = s.session_id
        WHERE s.session_type = 'R' AND s.location = ? AND s.data_source <> 'synthetic'
    """
    races, sc_races, vsc_races = con.execute(q, [location]).fetchall()[0]
    if not races:
        return None
    return (sc_races + 1) / (races + 2), (vsc_races + 1) / (races + 2), int(races)
