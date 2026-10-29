import numpy as np
import pandas as pd

from f1analytics import config
from f1analytics.columns import LAP_COLUMNS, conform
from f1analytics.sources.synthetic.calendar import COMPOUNDS, DRIVERS

SESSION_START = pd.Timedelta(minutes=57)
PIT_IN_SHARE = 0.4
PIT_OUT_SHARE = 0.6
TRAFFIC_PROB = 0.05
SC_SLOW = 1.30
VSC_SLOW = 1.25
EVOLUTION_PER_LAP = 0.004
LIGHT_FUEL_GAIN = config.START_FUEL_KG * config.FUEL_SEC_PER_KG


def _race_plan(n_laps, rng):
    if rng.random() < 0.7:
        pit = int(np.clip(round(n_laps * 0.45 + rng.normal(0, 4)), 12, n_laps - 12))
        first = rng.choice(["MEDIUM", "SOFT"], p=[0.7, 0.3])
        return [(first, 1, pit), ("HARD", pit + 1, n_laps)]
    p1 = int(np.clip(round(n_laps * 0.3 + rng.normal(0, 3)), 10, n_laps - 30))
    p2 = int(np.clip(round(n_laps * 0.65 + rng.normal(0, 3)), p1 + 10, n_laps - 8))
    return [("SOFT", 1, p1), ("HARD", p1 + 1, p2), ("MEDIUM", p2 + 1, n_laps)]


def _neutral_windows(track, n_laps, rng):
    status = np.array(["1"] * (n_laps + 1), dtype=object)
    if rng.random() < track.sc_prob:
        start = int(rng.integers(3, n_laps - 6))
        status[start:start + int(rng.integers(3, 6))] = config.SAFETY_CAR_CODE
    if rng.random() < track.vsc_prob:
        start = int(rng.integers(3, n_laps - 4))
        window = slice(start, start + 2)
        if (status[window] == "1").all():
            status[window] = config.VSC_CODE
    return status


def _speed_trap(track, pace, rng):
    if rng.random() < 0.02:
        return np.nan
    return round(track.top_speed_kmh - 6 * pace + rng.normal(0, 2.5), 1)


def _sectors(t):
    s1 = round(t * 0.31, 3)
    s2 = round(t * 0.38, 3)
    return s1, s2, round(t - s1 - s2, 3)


def generate_race(track, rng, n_laps=None):
    n_laps = n_laps or track.laps
    status = _neutral_windows(track, n_laps, rng)
    rows = []
    for code, number, team, pace in DRIVERS:
        plan = _race_plan(n_laps, rng)
        clock = 0.0
        for stint_no, (compound, first, last) in enumerate(plan, start=1):
            c = COMPOUNDS[compound]
            for lap in range(first, last + 1):
                tyre_life = lap - first + 1
                fuel = config.START_FUEL_KG * (1 - (lap - 1) / n_laps)
                t = (
                    track.base_lap_s + pace + c["offset"] + c["deg"] * tyre_life
                    + config.FUEL_SEC_PER_KG * fuel - EVOLUTION_PER_LAP * lap
                    + rng.normal(0, config.LAP_NOISE_SIGMA_S)
                )
                traffic = rng.random() < TRAFFIC_PROB
                if traffic:
                    t += rng.uniform(1.0, 3.0)
                ts = status[lap]
                if ts == config.SAFETY_CAR_CODE:
                    t *= SC_SLOW
                elif ts == config.VSC_CODE:
                    t *= VSC_SLOW
                in_lap = lap == last and stint_no < len(plan)
                out_lap = lap == first and stint_no > 1
                if in_lap:
                    t += PIT_IN_SHARE * track.pit_loss_s
                if out_lap:
                    t += PIT_OUT_SHARE * track.pit_loss_s + config.WARMUP_PENALTY_S
                if lap == 1:
                    t += 2.5
                start = clock
                clock += t
                s1, s2, s3 = _sectors(t)
                rows.append({
                    "Driver": code, "DriverNumber": number, "Team": team,
                    "LapNumber": float(lap), "Stint": float(stint_no),
                    "LapTime": t, "Sector1Time": s1, "Sector2Time": s2, "Sector3Time": s3,
                    "LapStart": start, "LapEnd": clock,
                    "PitIn": clock - 2.0 if in_lap else np.nan,
                    "PitOut": start + 8.0 if out_lap else np.nan,
                    "SpeedST": _speed_trap(track, pace, rng),
                    "Compound": compound, "TyreLife": float(tyre_life),
                    "TrackStatus": ts, "Deleted": False,
                    "IsAccurate": not (lap == 1 or in_lap or out_lap or ts != "1"),
                })
    df = pd.DataFrame(rows)
    df["Position"] = df.groupby("LapNumber")["LapEnd"].rank(method="first").astype(float)
    return _finish(df)


def _run(code, number, team, pace, compound, start_life, pushes, track, rng, clock, evo, cool_between):
    rows = []
    c = COMPOUNDS[compound]
    life = start_life
    light = track.base_lap_s - LIGHT_FUEL_GAIN
    seq = ["out"]
    for i in range(pushes):
        seq.append("push")
        if cool_between and i < pushes - 1:
            seq.append("cool")
    seq.append("in")
    for kind in seq:
        push = light + pace + c["offset"] + c["deg"] * life - evo + rng.normal(0, 0.15)
        if kind == "push":
            t = push
        elif kind == "cool":
            t = push * 1.30
        elif kind == "out":
            t = push * 1.35 + 0.4 * track.pit_loss_s
        else:
            t = push * 1.25 + 0.4 * track.pit_loss_s
        start = clock
        clock += t
        s1, s2, s3 = _sectors(t)
        rows.append({
            "Driver": code, "DriverNumber": number, "Team": team,
            "LapTime": t, "Sector1Time": s1, "Sector2Time": s2, "Sector3Time": s3,
            "LapStart": start, "LapEnd": clock,
            "PitIn": clock - 2.0 if kind == "in" else np.nan,
            "PitOut": start + 8.0 if kind == "out" else np.nan,
            "SpeedST": _speed_trap(track, pace, rng) if kind == "push" else round(track.top_speed_kmh * 0.85, 1),
            "Compound": compound, "TyreLife": float(life),
            "TrackStatus": "1", "Deleted": False,
            "IsAccurate": kind in {"push", "cool"},
        })
        life += 1
    return rows, clock


def generate_practice(track, code_name, rng):
    quali = code_name in {"Q", "SQ"}
    rows = []
    for code, number, team, pace in DRIVERS:
        clock = float(rng.uniform(0, 600))
        stint = 0
        runs = 4 if quali else 6
        for r in range(runs):
            stint += 1
            if quali:
                compound, pushes, cool = "SOFT", int(rng.integers(1, 3)), True
            elif r in (2, 3):
                compound, pushes, cool = str(rng.choice(["MEDIUM", "HARD"])), int(rng.integers(8, 14)), False
            else:
                compound, pushes, cool = str(rng.choice(["SOFT", "MEDIUM"])), int(rng.integers(1, 3)), True
            evo = 0.15 * r
            run_rows, clock = _run(code, number, team, pace, compound, 1, pushes, track, rng, clock, evo, cool)
            for row in run_rows:
                row["Stint"] = float(stint)
            rows.extend(run_rows)
            clock += float(rng.uniform(240, 600))
    df = pd.DataFrame(rows)
    df["LapNumber"] = df.groupby("Driver").cumcount().astype(float) + 1
    df["Position"] = np.nan
    return _finish(df)


def _finish(df):
    td = lambda s: pd.to_timedelta(s, unit="s") + SESSION_START
    out = pd.DataFrame({
        "Time": td(df["LapEnd"]),
        "Driver": df["Driver"],
        "DriverNumber": df["DriverNumber"],
        "Team": df["Team"],
        "LapTime": pd.to_timedelta(df["LapTime"].round(3), unit="s"),
        "LapNumber": df["LapNumber"],
        "Stint": df["Stint"],
        "PitOutTime": td(df["PitOut"]),
        "PitInTime": td(df["PitIn"]),
        "Sector1Time": pd.to_timedelta(df["Sector1Time"], unit="s"),
        "Sector2Time": pd.to_timedelta(df["Sector2Time"], unit="s"),
        "Sector3Time": pd.to_timedelta(df["Sector3Time"], unit="s"),
        "SpeedST": df["SpeedST"],
        "Compound": df["Compound"],
        "TyreLife": df["TyreLife"],
        "LapStartTime": td(df["LapStart"]),
        "TrackStatus": df["TrackStatus"],
        "Position": df["Position"],
        "Deleted": df["Deleted"],
        "IsAccurate": df["IsAccurate"],
    })
    out = out.sort_values(["Driver", "LapNumber"]).reset_index(drop=True)
    return conform(out, LAP_COLUMNS)


def generate_laps(track, session_code, rng):
    if session_code in config.RACE_CODES:
        n = track.laps if session_code == "R" else max(15, track.laps // 3)
        return generate_race(track, rng, n)
    return generate_practice(track, session_code, rng)
