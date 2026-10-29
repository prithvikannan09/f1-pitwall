PIT_LOSS_S = {
    "mexico": 22.5,
    "austin": 20.5,
    "são paulo": 21.5,
    "sao paulo": 21.5,
    "interlagos": 21.5,
    "las vegas": 20.0,
    "lusail": 25.0,
    "yas": 21.5,
    "yas marina": 21.5,
    "abu dhabi": 21.5,
    "monza": 24.0,
    "spa": 19.5,
    "sakhir": 22.5,
    "bahrain": 22.5,
    "silverstone": 20.0,
    "singapore": 26.5,
    "baku": 20.5,
    "zandvoort": 21.5,
    "suzuka": 22.5,
    "melbourne": 19.5,
    "imola": 28.0,
    "monaco": 20.0,
    "montréal": 18.5,
    "montreal": 18.5,
    "barcelona": 22.0,
    "spielberg": 20.0,
    "budapest": 20.5,
    "jeddah": 20.0,
    "shanghai": 22.5,
    "miami": 20.5,
    "madrid": 21.0,
}
DEFAULT_PIT_LOSS_S = 22.0

COMPOUND_PRIORS = {
    "SOFT": {"offset": 0.0, "deg": 0.09},
    "MEDIUM": {"offset": 0.35, "deg": 0.06},
    "HARD": {"offset": 0.70, "deg": 0.04},
    "INTERMEDIATE": {"offset": 0.0, "deg": 0.05},
    "WET": {"offset": 0.0, "deg": 0.04},
}
DRY = ("SOFT", "MEDIUM", "HARD")


def pit_loss_for(circuit):
    key = str(circuit or "").strip().lower()
    for name, value in PIT_LOSS_S.items():
        if key and (name in key or key in name):
            return value, True
    return DEFAULT_PIT_LOSS_S, False
