from itertools import product

import numpy as np
import pandas as pd
from scipy import stats

from f1analytics import config
from f1analytics.analysis.degradation import fit_stint, fit_stints
from f1analytics.analysis.fuel import fuel_corrected
from f1analytics.analysis.laps import clean_laps, seconds
from f1analytics.analysis.pit_window import stint_time
from f1analytics.columns import LAP_COLUMNS, conform
from f1analytics.pitwall.tracks import COMPOUND_PRIORS, DRY, pit_loss_for
from f1analytics.simulator.monte_carlo import simulate
from f1analytics.simulator.scenario import UndercutScenario

WINDOW_TOL_S = 1.0
MIN_STINT = 3
CLEAR_AIR_S = 1.0
DOUBLE_STACK_GAP_S = 5.0
QUEUE_LOSS_S = (3.0, 4.0, 6.0)
SIM_RUNS = 3000
FULL_TRUST_LAPS = 60
DEG_FLOOR_FRAC = 0.5
DEG_CEIL_FRAC = 3.0
PERSONAL_FULL_LAPS = 10
PERSONAL_DELTA_CAP_S = 2.0
PIT_LOSS_MIN_STOPS = 4
PIT_LOSS_TRUST_FRAC = 0.25
NEUTRAL = {"4": "SC", "6": "VSC", "7": "VSC ending", "5": "Red flag"}


def laps_frame(snapshot):
    team = {d["number"]: d.get("team") for d in snapshot.get("drivers", [])}
    rows = snapshot.get("laps") or []
    if not rows:
        return conform(pd.DataFrame(), LAP_COLUMNS)
    df = pd.DataFrame(rows)
    status = df["track_status"].fillna("1").astype(str)
    lt = pd.to_numeric(df["lap_time"], errors="coerce")
    out = pd.DataFrame({
        "Driver": df["code"],
        "DriverNumber": df["number"].astype(str),
        "Team": df["number"].astype(str).map(team),
        "LapNumber": df["lap"].astype(float),
        "LapTime": pd.to_timedelta(lt, unit="s"),
        "Stint": pd.to_numeric(df["stint"], errors="coerce"),
        "Compound": df["compound"],
        "TyreLife": pd.to_numeric(df["tyre_age"], errors="coerce"),
        "PitInTime": pd.to_timedelta(np.where(df["pit_in"].fillna(False), 0.0, np.nan), unit="s"),
        "PitOutTime": pd.to_timedelta(np.where(df["pit_out"].fillna(False), 0.0, np.nan), unit="s"),
        "TrackStatus": status,
        "Deleted": False,
    })
    out["IsAccurate"] = lt.notna() & ~df["pit_in"].fillna(False).astype(bool) & ~df["pit_out"].fillna(False).astype(bool) & (status == "1") & (out["LapNumber"] > 1)
    return conform(out, LAP_COLUMNS)


def total_laps(snapshot):
    s = snapshot.get("session") or {}
    return int(s.get("total_laps") or 0) or max([d.get("laps", 0) for d in snapshot.get("drivers", [])] + [1])


def compound_table(laps_df, total):
    priors = {c: dict(v) for c, v in COMPOUND_PRIORS.items()}
    clean = clean_laps(laps_df)
    base = None
    if len(clean):
        fc = fuel_corrected(clean, total)
        adj = fc["FuelCorrected"] - fc["Compound"].map(lambda c: priors.get(str(c), priors["MEDIUM"])["offset"]) - fc["TyreLife"].fillna(0) * fc["Compound"].map(lambda c: priors.get(str(c), priors["MEDIUM"])["deg"])
        base = float(adj.median()) if adj.notna().any() else None
    stints = fit_stints(laps_df, total, True) if len(clean) else pd.DataFrame()
    table = {}
    for comp, prior in priors.items():
        alpha_p = (base if base is not None else 90.0) + prior["offset"]
        rows = stints[stints["Compound"] == comp] if len(stints) else stints
        n = int(len(rows))
        laps_seen = int(rows["n"].sum()) if n else 0
        w = min(1.0, laps_seen / FULL_TRUST_LAPS) if n >= 2 else min(0.5, laps_seen / FULL_TRUST_LAPS)
        if n:
            alpha = w * float(rows["alpha"].median()) + (1 - w) * alpha_p
            beta = w * float(rows["beta"].median()) + (1 - w) * prior["deg"]
            src = "measured" if w >= 0.99 else f"blend {w:.0%} measured"
        else:
            alpha, beta, src = alpha_p, prior["deg"], "estimate"
        beta = float(np.clip(beta, DEG_FLOOR_FRAC * prior["deg"], DEG_CEIL_FRAC * prior["deg"]))
        table[comp] = {"alpha": alpha, "beta": beta, "source": src, "stints": n, "laps": laps_seen}
    return table, stints


def _rule_ok(used, extra, wet):
    if wet:
        return True
    dry = {c for c in set(used) | set(extra) if c in DRY}
    return len(dry) >= 2


def personal_model(laps_df, car, total, table):
    comp = table.get(car.get("compound")) or table["MEDIUM"]
    rows = laps_df[(laps_df["DriverNumber"] == car["number"]) & (laps_df["Stint"] == car.get("stint"))]
    rows = rows[rows["IsAccurate"].astype(bool)].sort_values("LapNumber")
    n = len(rows)
    if n < 3:
        return None
    fc = fuel_corrected(rows, total)
    ages = fc["TyreLife"].astype(float).to_numpy()
    times = fc["FuelCorrected"].astype(float).to_numpy()
    slope = None
    if n >= 5 and len(np.unique(ages)) >= 4:
        slope = max(fit_stint(ages, times)["beta"], 0.0)
    w = min(1.0, n / PERSONAL_FULL_LAPS) if slope is not None else 0.0
    beta = w * slope + (1 - w) * comp["beta"] if slope is not None else comp["beta"]
    prior = COMPOUND_PRIORS.get(car.get("compound") or "MEDIUM", COMPOUND_PRIORS["MEDIUM"])["deg"]
    beta = max(beta, DEG_FLOOR_FRAC * prior)
    recent = slice(max(0, n - 3), n)
    alpha0 = float(np.median(times[recent] - beta * ages[recent]))
    delta = float(np.clip(alpha0 - comp["alpha"], -PERSONAL_DELTA_CAP_S, PERSONAL_DELTA_CAP_S))
    return {"alpha": alpha0, "beta": float(beta), "delta": delta, "laps": n, "own_slope": slope, "weight": w}


def personalise(table, car, personal):
    if not personal:
        return table
    out = {c: dict(v, alpha=v["alpha"] + personal["delta"]) for c, v in table.items()}
    cur = car.get("compound") or "MEDIUM"
    out[cur] = dict(out.get(cur, out["MEDIUM"]), alpha=personal["alpha"], beta=personal["beta"], source="this driver's stint")
    return out


def pit_loss_estimate(laps_df, default):
    if not len(laps_df):
        return None, 0
    df = laps_df.assign(S=seconds(laps_df["LapTime"]))
    clean = df[df["IsAccurate"].astype(bool)]
    ref = clean.groupby("DriverNumber")["S"].median()
    losses = []
    for num, rows in df.groupby("DriverNumber"):
        if num not in ref.index:
            continue
        rows = rows.set_index("LapNumber")
        for lap in rows.index[rows["PitInTime"].notna()]:
            if lap + 1 not in rows.index or pd.isna(rows.at[lap + 1, "PitOutTime"]):
                continue
            if str(rows.at[lap, "TrackStatus"]) != "1" or str(rows.at[lap + 1, "TrackStatus"]) != "1":
                continue
            value = rows.at[lap, "S"] + rows.at[lap + 1, "S"] - 2 * ref[num]
            if np.isfinite(value):
                losses.append(value)
    if len(losses) < PIT_LOSS_MIN_STOPS:
        return None, len(losses)
    est = float(np.median(losses))
    if abs(est - default) > PIT_LOSS_TRUST_FRAC * default:
        return None, len(losses)
    return est, len(losses)


def plan_options(table, c0, age0, laps_left, pit_loss, used, max_stops=2, min_stint=MIN_STINT):
    rows = []
    if laps_left <= 0:
        return pd.DataFrame(columns=["stops", "compounds", "pit_after", "total"])
    wet = any(c in ("INTERMEDIATE", "WET") for c in set(used) | {c0})
    cur = table.get(c0) or table["MEDIUM"]
    a0, b0 = cur["alpha"], cur["beta"]
    start = age0 + 1
    if _rule_ok(used, [], wet):
        rows.append({"stops": 0, "compounds": (), "pit_after": (), "total": float(stint_time(a0, b0, laps_left, start))})
    choices = [c for c in DRY] if not wet else [c0]
    if max_stops >= 1 and laps_left > min_stint:
        p = np.arange(1, laps_left - min_stint + 1)
        first = stint_time(a0, b0, p, start)
        for c in choices:
            if not _rule_ok(used, [c], wet):
                continue
            t = first + pit_loss + stint_time(table[c]["alpha"], table[c]["beta"], laps_left - p, 1)
            for pi, ti in zip(p, t):
                rows.append({"stops": 1, "compounds": (c,), "pit_after": (int(pi),), "total": float(ti)})
    if max_stops >= 2 and laps_left > 2 * min_stint:
        p1, p2 = np.meshgrid(np.arange(1, laps_left + 1), np.arange(1, laps_left + 1), indexing="ij")
        l2, l3 = p2 - p1, laps_left - p2
        ok = (l2 >= min_stint) & (l3 >= min_stint)
        first = stint_time(a0, b0, p1, start)
        for c1, c2 in product(choices, repeat=2):
            if not _rule_ok(used, [c1, c2], wet):
                continue
            t = first + 2 * pit_loss + stint_time(table[c1]["alpha"], table[c1]["beta"], l2, 1) + stint_time(table[c2]["alpha"], table[c2]["beta"], l3, 1)
            t = np.where(ok, t, np.inf)
            i, j = np.unravel_index(np.argmin(t), t.shape)
            if np.isfinite(t[i, j]):
                rows.append({"stops": 2, "compounds": (c1, c2), "pit_after": (int(p1[i, j]), int(p2[i, j])), "total": float(t[i, j])})
                for pi in np.unique(p1[ok]):
                    k = np.argmin(np.where(ok[pi - 1], t[pi - 1], np.inf))
                    if np.isfinite(t[pi - 1, k]):
                        rows.append({"stops": 2, "compounds": (c1, c2), "pit_after": (int(pi), int(p2[pi - 1, k])), "total": float(t[pi - 1, k])})
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["stops", "compounds", "pit_after", "total"])
    df = df.sort_values("total").drop_duplicates(["stops", "compounds", "pit_after"]).reset_index(drop=True)
    df["delta"] = df["total"] - df["total"].iloc[0]
    return df


def running_order(snapshot):
    cars = [d for d in snapshot.get("drivers", []) if not d.get("retired") and d.get("position")]
    return sorted(cars, key=lambda d: d["position"])


def rejoin(snapshot, driver, loss):
    me = driver.get("gap_to_leader")
    if me is None:
        return None
    target = me + loss
    others = [d for d in running_order(snapshot) if d["number"] != driver["number"] and d.get("gap_to_leader") is not None]
    ahead = [d for d in others if d["gap_to_leader"] < target]
    behind = [d for d in others if d["gap_to_leader"] >= target]
    car_ahead = max(ahead, key=lambda d: d["gap_to_leader"]) if ahead else None
    car_behind = min(behind, key=lambda d: d["gap_to_leader"]) if behind else None
    gap_ahead = target - car_ahead["gap_to_leader"] if car_ahead else None
    return {
        "position": len(ahead) + 1,
        "positions_lost": len(ahead) + 1 - driver["position"],
        "car_ahead": car_ahead["code"] if car_ahead else None,
        "car_ahead_tyres": f"{car_ahead['compound']} {car_ahead['tyre_age']}L" if car_ahead else None,
        "gap_ahead": gap_ahead,
        "car_behind": car_behind["code"] if car_behind else None,
        "gap_behind": car_behind["gap_to_leader"] - target if car_behind else None,
        "traffic": gap_ahead is not None and gap_ahead < CLEAR_AIR_S,
    }


def _neighbour(snapshot, driver, step):
    order = running_order(snapshot)
    idx = next((i for i, d in enumerate(order) if d["number"] == driver["number"]), None)
    if idx is None:
        return None
    j = idx + step
    return order[j] if 0 <= j < len(order) else None


def _next_compound(car, laps_left, table):
    used = set(car.get("compounds_used") or [])
    prefs = ["HARD", "MEDIUM", "SOFT"] if laps_left > 25 else (["MEDIUM", "HARD", "SOFT"] if laps_left > 12 else ["SOFT", "MEDIUM", "HARD"])
    for c in prefs:
        if len({x for x in used | {c} if x in DRY}) >= 2 or c != car.get("compound"):
            return c
    return prefs[0]


def _fresh_delta(table, old_c, old_age, new_c):
    old = table.get(old_c) or table["MEDIUM"]
    new = table.get(new_c) or table["MEDIUM"]
    return (old["alpha"] + old["beta"] * (old_age + 1)) - (new["alpha"] + new["beta"])


def needs_stop(car, table, pit_loss, total):
    laps_left = max(total - car["laps"], 0)
    used = car.get("compounds_used") or ([car["compound"]] if car.get("compound") else [])
    plans = plan_options(table, car.get("compound") or "MEDIUM", car.get("tyre_age") or 0, laps_left, pit_loss, used, max_stops=1)
    return bool(len(plans)) and int(plans.iloc[0]["stops"]) > 0


def undercut_duel(snapshot, attacker, target, gap, table, pit_loss, total, seed=7, new_compound=None):
    if attacker is None or target is None or gap is None or gap > 15:
        return None
    if attacker.get("team") and attacker.get("team") == target.get("team"):
        return {"attacker": attacker["code"], "target": target["code"], "gap": float(gap), "probability": None,
                "note": f"{attacker['code'] if attacker.get('team') else ''} and {target['code']} are teammates: no undercut fight."}
    if attacker.get("in_pit") or target.get("in_pit"):
        return None
    laps_left = total - attacker["laps"]
    if laps_left < 3:
        return None
    if not needs_stop(attacker, table, pit_loss, total) or not needs_stop(target, table, pit_loss, total):
        return {"attacker": attacker["code"], "target": target["code"], "gap": float(gap), "probability": None,
                "note": f"No undercut fight: {attacker['code'] if not needs_stop(attacker, table, pit_loss, total) else target['code']} has no stop left to make."}
    new_c = new_compound or _next_compound(attacker, laps_left, table)
    fresh = _fresh_delta(table, target["compound"], target["tyre_age"], new_c)
    behind_attacker = [d["gap_to_leader"] - attacker["gap_to_leader"] for d in running_order(snapshot)
                       if d.get("gap_to_leader") is not None and attacker.get("gap_to_leader") is not None
                       and d["gap_to_leader"] > attacker["gap_to_leader"]]
    sc = UndercutScenario(
        gap=float(gap), k=1, pit_loss=float(pit_loss), fresh_delta=float(fresh),
        deg_old=(table.get(target["compound"]) or table["MEDIUM"])["beta"],
        deg_new=(table.get(new_c) or table["MEDIUM"])["beta"],
        total_laps=int(total), field_gaps=tuple(round(g, 2) for g in behind_attacker[:10]),
    )
    s = simulate(sc, n=SIM_RUNS, seed=seed).summary()
    return {
        "attacker": attacker["code"], "target": target["code"], "gap": float(gap),
        "new_compound": new_c, "fresh_delta": float(fresh),
        "probability": s["success_prob"], "ci": (s["ci_low"], s["ci_high"]), "gain_p50": s["gain_p50"], "note": None,
    }


def stint_wear(laps_df, driver, total):
    rows = laps_df[(laps_df["DriverNumber"] == driver["number"]) & (laps_df["Stint"] == driver.get("stint"))]
    rows = rows[rows["IsAccurate"].astype(bool)]
    fc = fuel_corrected(rows, total) if len(rows) else rows
    series = [{"age": float(a), "time": float(t)} for a, t in zip(fc["TyreLife"], fc["FuelCorrected"])] if len(rows) else []
    if len(rows) < 5 or rows["TyreLife"].nunique() < 4:
        return {"slope": None, "laps": int(len(rows)), "r2": None, "series": series}
    fit = fit_stint(fc["TyreLife"].astype(float), fc["FuelCorrected"].astype(float))
    return {"slope": float(fit["beta"]), "laps": int(fit["n"]), "r2": float(fit["r2"]), "series": series}


def analyse(snapshot, team="Ferrari", pit_loss=None):
    total = total_laps(snapshot)
    session = snapshot.get("session") or {}
    laps_df = laps_frame(snapshot)
    table, _ = compound_table(laps_df, total)
    default_loss, known = pit_loss_for(session.get("circuit") or session.get("meeting"))
    measured, n_stops = pit_loss_estimate(laps_df, default_loss)
    loss = float(pit_loss) if pit_loss else (measured if measured else default_loss)
    loss_source = "set by you" if pit_loss else (f"measured from {n_stops} green-flag stops this race" if measured else ("track default (est.)" if known else "generic default (est.)"))
    status = str(session.get("track_status") or "1")
    cars = [d for d in running_order(snapshot) if team.lower() in str(d.get("team") or "").lower()]
    reports = []
    for car in cars:
        laps_left = max(total - car["laps"], 0)
        used = car.get("compounds_used") or ([car["compound"]] if car.get("compound") else [])
        personal = personal_model(laps_df, car, total, table)
        mine = personalise(table, car, personal)
        plans = plan_options(mine, car.get("compound") or "MEDIUM", car.get("tyre_age") or 0, laps_left, loss, used)
        best = plans.iloc[0] if len(plans) else None
        stop_plans = plans[plans["stops"] > 0] if len(plans) else plans
        now = stop_plans[stop_plans["pit_after"].map(lambda t: t[0] == 1)] if len(stop_plans) else stop_plans
        now_best = now.iloc[0] if len(now) else None
        near = stop_plans[stop_plans["delta"] <= WINDOW_TOL_S] if len(stop_plans) else stop_plans
        firsts = sorted({t[0] for t in near["pit_after"]}) if len(near) else []
        window = (car["laps"] + firsts[0], car["laps"] + firsts[-1]) if firsts else None
        rj_now = rejoin(snapshot, car, loss)
        call, why = _call(car, best, now_best, window, rj_now, laps_left)
        ahead, behind = _neighbour(snapshot, car, -1), _neighbour(snapshot, car, +1)
        our_next = (now_best["compounds"][0] if now_best is not None else None) or (best["compounds"][0] if best is not None and len(best["compounds"]) else None)
        attack = undercut_duel(snapshot, car, ahead, car.get("interval"), mine, loss, total, new_compound=our_next) if ahead else None
        defend = undercut_duel(snapshot, behind, car, behind.get("interval") if behind else None, table, loss, total) if behind else None
        sc_plan = _sc_plan(snapshot, car, best, loss, laps_left)
        wear = stint_wear(laps_df, car, total)
        comp = table.get(car.get("compound")) or table["MEDIUM"]
        reports.append({
            "car": car,
            "laps_left": laps_left,
            "call": call,
            "why": why,
            "best_plan": None if best is None else {"stops": int(best["stops"]), "compounds": list(best["compounds"]), "pit_laps": [car["laps"] + p for p in best["pit_after"]], "total": float(best["total"])},
            "alt_plan": _alt(plans, car),
            "box_now_cost": None if (now_best is None or best is None) else float(now_best["total"] - best["total"]),
            "box_now_compound": None if now_best is None else now_best["compounds"][0],
            "window": window,
            "rejoin_now": rj_now,
            "attack": attack,
            "defend": defend,
            "safety_car": sc_plan,
            "wear": {
                "stint_slope": wear["slope"],
                "stint_laps": wear["laps"],
                "series": wear["series"],
                "compound_slope": comp["beta"],
                "compound_source": comp["source"],
                "loss_vs_new": comp["beta"] * (car.get("tyre_age") or 0),
                "pace_vs_field": personal["delta"] if personal else None,
                "plan_slope": (personal or {}).get("beta"),
            },
            "ahead": ahead,
            "behind": behind,
            "plans": plans.head(12),
        })
    _double_stack(reports)
    return {
        "lap": session.get("lap"), "total_laps": total, "track_status": status,
        "neutralised": NEUTRAL.get(status),
        "pit_loss": loss, "pit_loss_source": loss_source,
        "compounds": table, "cars": reports,
    }


def _alt(plans, car):
    if not len(plans):
        return None
    others = plans[plans["stops"] != plans.iloc[0]["stops"]]
    if not len(others):
        return None
    o = others.iloc[0]
    return {"stops": int(o["stops"]), "compounds": list(o["compounds"]), "pit_laps": [car["laps"] + x for x in o["pit_after"]], "delta": float(o["delta"])}


def _call(car, best, now_best, window, rj, laps_left):
    if car.get("in_pit"):
        return "IN PIT", "Car is in the pit lane now."
    if best is None or laps_left <= 1:
        return "STAY OUT", "Last lap: bring it home."
    if int(best["stops"]) == 0:
        return "STAY OUT", f"No more stops needed: current {car['compound']} tyres reach the flag fastest."
    if now_best is not None and now_best["total"] - best["total"] <= WINDOW_TOL_S:
        tail = ""
        if rj and rj["traffic"] and window and window[1] > car["laps"] + 1:
            return "BOX NEXT LAP", f"In the window, but boxing now drops you {rj['gap_ahead']:.1f}s behind {rj['car_ahead']} (traffic). Next lap is still inside the window."
        if rj:
            tail = f" Rejoin P{rj['position']}" + (f", {rj['gap_ahead']:.1f}s behind {rj['car_ahead']}" if rj["car_ahead"] else "") + "."
        return "BOX THIS LAP", f"Inside the optimal window for {now_best['compounds'][0]}.{tail}"
    lo, hi = window if window else (None, None)
    return "STAY OUT", (f"Pit window opens lap {lo}–{hi}." if window else "Pitting now costs time.")


def _sc_plan(snapshot, car, best, loss, laps_left):
    out = {}
    needs_stop = best is not None and int(best["stops"]) > 0
    for label, factor in (("SC", config.SC_PIT_FACTOR), ("VSC", config.VSC_PIT_FACTOR)):
        cheap = loss * factor
        rj = rejoin(snapshot, car, cheap)
        box = needs_stop and laps_left >= 4 and not car.get("in_pit")
        out[label] = {
            "box": box,
            "pit_loss": cheap,
            "saving": loss - cheap,
            "rejoin": rj,
            "reason": (f"Stop still needed: a {label} stop costs ~{cheap:.0f}s instead of {loss:.0f}s (saves ~{loss - cheap:.0f}s)."
                       if box else ("In the pit lane now." if car.get("in_pit")
                                    else ("No more stops needed: stay out and keep track position." if not needs_stop
                                          else "Too late in the race to gain from a stop."))),
        }
    return out


def _double_stack(reports):
    boxing = [r for r in reports if r["safety_car"]["SC"]["box"]]
    if len(boxing) < 2:
        for r in reports:
            r["double_stack"] = None
        return
    a, b = sorted(boxing, key=lambda r: r["car"]["position"])[:2]
    gap = abs((b["car"].get("gap_to_leader") or 0) - (a["car"].get("gap_to_leader") or 0))
    risk = gap < DOUBLE_STACK_GAP_S
    note = {
        "first": a["car"]["code"], "second": b["car"]["code"], "gap": gap, "risk": risk,
        "queue_loss_est": QUEUE_LOSS_S if risk else None,
        "advice": (f"Double-stack under SC: {a['car']['code']} first, {b['car']['code']} queues ~{QUEUE_LOSS_S[0]:.0f}–{QUEUE_LOSS_S[2]:.0f}s (est.) because they are only {gap:.1f}s apart."
                   if risk else f"Both can box under SC: {gap:.1f}s apart, no queue expected."),
    }
    for r in reports:
        r["double_stack"] = note


def start_tyre_options(snapshot, pit_loss=None):
    from f1analytics.pitwall.tracks import race_laps_for

    session = snapshot.get("session") or {}
    race = str(session.get("type") or "").lower() in ("race", "sprint")
    total = (total_laps(snapshot) if race else None) or race_laps_for(session.get("circuit"), session.get("meeting")) or 60
    laps_df = laps_frame(snapshot)
    table, _ = compound_table(laps_df, total)
    loss = float(pit_loss) if pit_loss else pit_loss_for(session.get("circuit") or session.get("meeting"))[0]
    rows = []
    for c in DRY:
        plans = plan_options(table, c, 0, total, loss, [c])
        if not len(plans):
            continue
        best = plans.iloc[0]
        rows.append({"compound": c, "stops": int(best["stops"]), "next": list(best["compounds"]), "pit_laps": list(best["pit_after"]), "total": float(best["total"]),
                     "source": table[c]["source"]})
    rows.sort(key=lambda r: r["total"])
    for r in rows:
        r["delta"] = r["total"] - rows[0]["total"]
    return {"laps": total, "pit_loss": loss, "options": rows}
