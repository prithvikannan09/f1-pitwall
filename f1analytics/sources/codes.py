ALIASES = {
    "FP1": "FP1", "PRACTICE 1": "FP1", "P1": "FP1",
    "FP2": "FP2", "PRACTICE 2": "FP2", "P2": "FP2",
    "FP3": "FP3", "PRACTICE 3": "FP3", "P3": "FP3",
    "Q": "Q", "QUALIFYING": "Q", "QUALI": "Q",
    "SQ": "SQ", "SPRINT QUALIFYING": "SQ", "SPRINT SHOOTOUT": "SQ", "SS": "SQ",
    "S": "S", "SPRINT": "S",
    "R": "R", "RACE": "R",
}


def normalise_session(value):
    code = ALIASES.get(str(value).strip().upper())
    if code is None:
        raise ValueError(f"Unknown session {value!r}; use one of FP1 FP2 FP3 SQ S Q R")
    return code
