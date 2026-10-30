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


CIRCUIT_KEYS = {
    "silverstone": 2, "hungaroring": 4, "budapest": 4, "imola": 6, "spa": 7, "austin": 9, "united states": 9,
    "melbourne": 10, "albert park": 10, "interlagos": 14, "sao paulo": 14, "são paulo": 14, "catalunya": 15, "barcelona": 15,
    "spielberg": 19, "red bull ring": 19, "monaco": 22, "monte carlo": 22, "montreal": 23, "montréal": 23, "canada": 23,
    "monza": 39, "suzuka": 46, "japan": 46, "shanghai": 49, "china": 49, "zandvoort": 55, "singapore": 61, "marina bay": 61,
    "sakhir": 63, "bahrain": 63, "mexico": 65, "yas marina": 70, "abu dhabi": 70, "baku": 144, "azerbaijan": 144,
    "jeddah": 149, "saudi": 149, "lusail": 150, "qatar": 150, "miami": 151, "las vegas": 152, "madring": 153, "madrid": 153,
}


def circuit_key_for(*names):
    for name in names:
        key = str(name or "").strip().lower()
        if not key:
            continue
        for alias, value in CIRCUIT_KEYS.items():
            if alias in key:
                return value
    return None
