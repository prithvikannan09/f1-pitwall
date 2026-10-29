from f1analytics import config
from f1analytics.analysis.laps import seconds


def fuel_mass(lap_number, total_laps, start_fuel_kg=config.START_FUEL_KG):
    return start_fuel_kg * (1 - (lap_number - 1) / total_laps)


def fuel_effect(lap_number, total_laps, start_fuel_kg=config.START_FUEL_KG, sec_per_kg=config.FUEL_SEC_PER_KG):
    return sec_per_kg * fuel_mass(lap_number, total_laps, start_fuel_kg)


def fuel_gain_per_lap(total_laps, start_fuel_kg=config.START_FUEL_KG, sec_per_kg=config.FUEL_SEC_PER_KG):
    return sec_per_kg * start_fuel_kg / total_laps


def fuel_corrected(laps, total_laps, start_fuel_kg=config.START_FUEL_KG, sec_per_kg=config.FUEL_SEC_PER_KG):
    out = laps.copy()
    raw = seconds(out["LapTime"])
    out["LapTimeSeconds"] = raw
    out["FuelCorrected"] = raw - fuel_effect(out["LapNumber"], total_laps, start_fuel_kg, sec_per_kg)
    return out
