from itertools import product

import numpy as np
import pandas as pd

from f1analytics import config


def stint_time(alpha, beta, length, start_age=1):
    length = np.asarray(length, dtype=float)
    return length * alpha + beta * (length * start_age + length * (length - 1) / 2)


def one_stop_optimum(alpha1, beta1, alpha2, beta2, total_laps, start_age=1):
    return (alpha2 - alpha1 + (beta2 - beta1) * (start_age - 0.5) + beta2 * total_laps) / (beta1 + beta2)


def optimise(total_laps, pit_loss, models, max_stops=2, min_stint=config.MIN_STINT_LAPS, start_compound=None, start_age=1):
    comps = sorted(models)
    rows = []
    n = int(total_laps)
    for stops in range(1, max_stops + 1):
        for seq in product(comps, repeat=stops + 1):
            if len(set(seq)) < 2 or (start_compound and seq[0] != start_compound):
                continue
            rows.extend(_plans(seq, n, pit_loss, models, min_stint, start_age))
    if not rows:
        return pd.DataFrame(columns=["stops", "compounds", "pit_laps", "total_time", "delta"])
    df = pd.DataFrame(rows).sort_values("total_time").reset_index(drop=True)
    df["delta"] = df["total_time"] - df["total_time"].iloc[0]
    return df


def _plans(seq, n, pit_loss, models, min_stint, start_age):
    stops = len(seq) - 1
    out = []
    if stops == 1:
        p = np.arange(min_stint, n - min_stint + 1)
        a1, b1 = models[seq[0]]
        a2, b2 = models[seq[1]]
        t = stint_time(a1, b1, p, start_age) + stint_time(a2, b2, n - p, 1) + pit_loss
        for lap, total in zip(p, t):
            out.append({"stops": 1, "compounds": "-".join(seq), "pit_laps": (int(lap),), "total_time": float(total)})
        return out
    if stops == 2:
        p1, p2 = np.meshgrid(np.arange(min_stint, n + 1), np.arange(min_stint, n + 1), indexing="ij")
        l1, l2 = p1, p2 - p1
        l3 = n - p2
        ok = (l2 >= min_stint) & (l3 >= min_stint)
        (a1, b1), (a2, b2), (a3, b3) = (models[c] for c in seq)
        t = stint_time(a1, b1, l1, start_age) + stint_time(a2, b2, l2, 1) + stint_time(a3, b3, l3, 1) + 2 * pit_loss
        for i, j in zip(*np.nonzero(ok)):
            out.append({"stops": 2, "compounds": "-".join(seq), "pit_laps": (int(p1[i, j]), int(p2[i, j])), "total_time": float(t[i, j])})
    return out


def best_per_strategy(plans):
    if plans.empty:
        return plans
    return plans.loc[plans.groupby(["stops", "compounds"])["total_time"].idxmin()].sort_values("total_time").reset_index(drop=True)


def pit_window(plans, compounds, tolerance=config.PIT_WINDOW_TOLERANCE_S):
    sub = plans[plans["compounds"] == compounds]
    if sub.empty:
        return sub
    best = sub["total_time"].min()
    return sub[sub["total_time"] <= best + tolerance].sort_values("pit_laps")
