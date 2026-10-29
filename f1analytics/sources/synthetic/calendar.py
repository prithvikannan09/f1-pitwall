from dataclasses import dataclass

import pandas as pd

DRIVERS = [
    ("VER", "1", "Red Bull Racing", 0.00),
    ("PER", "11", "Red Bull Racing", 0.45),
    ("NOR", "4", "McLaren", 0.05),
    ("PIA", "81", "McLaren", 0.20),
    ("LEC", "16", "Ferrari", 0.10),
    ("SAI", "55", "Ferrari", 0.15),
    ("HAM", "44", "Mercedes", 0.25),
    ("RUS", "63", "Mercedes", 0.28),
    ("ALO", "14", "Aston Martin", 0.70),
    ("STR", "18", "Aston Martin", 0.95),
    ("GAS", "10", "Alpine", 0.80),
    ("OCO", "31", "Alpine", 0.85),
    ("ALB", "23", "Williams", 0.90),
    ("COL", "43", "Williams", 1.05),
    ("TSU", "22", "RB", 0.75),
    ("LAW", "30", "RB", 0.85),
    ("HUL", "27", "Haas F1 Team", 0.70),
    ("MAG", "20", "Haas F1 Team", 0.88),
    ("BOT", "77", "Kick Sauber", 1.15),
    ("ZHO", "24", "Kick Sauber", 1.25),
]

COMPOUNDS = {
    "SOFT": {"offset": 0.0, "deg": 0.090},
    "MEDIUM": {"offset": 0.35, "deg": 0.060},
    "HARD": {"offset": 0.70, "deg": 0.040},
}


@dataclass(frozen=True)
class TrackProfile:
    key: str
    laps: int
    length_m: float
    base_lap_s: float
    top_speed_kmh: float
    corners: tuple
    drs_zones: tuple
    pit_loss_s: float
    air_temp_c: tuple
    sc_prob: float
    vsc_prob: float
    pressure_hpa: float


TRACKS = {
    "mexico": TrackProfile(
        "mexico", 71, 4304.0, 79.5, 352.0,
        ((1310, 95), (1420, 125), (1560, 150), (1930, 115), (2150, 135),
         (2420, 170), (2560, 180), (2700, 175), (2880, 160), (3260, 75),
         (3420, 80), (3640, 85), (3870, 115), (4060, 140)),
        ((0, 1180), (1640, 1900), (4150, 4304)),
        22.0, (19.0, 23.0), 0.50, 0.40, 780.0,
    ),
    "spa": TrackProfile(
        "spa", 44, 7004.0, 105.0, 335.0,
        ((380, 75), (700, 250), (1900, 140), (2350, 170), (2900, 115),
         (3350, 215), (3800, 125), (4100, 145), (4900, 250), (5350, 290),
         (6450, 80), (6650, 110)),
        ((0, 300), (1450, 1880)),
        19.5, (16.0, 21.0), 0.45, 0.35, 975.0,
    ),
    "monza": TrackProfile(
        "monza", 53, 5793.0, 81.0, 350.0,
        ((870, 85), (1010, 95), (1620, 195), (2380, 120), (2520, 150),
         (3300, 115), (3420, 140), (4330, 190), (5200, 215)),
        ((0, 750), (3700, 4250)),
        24.0, (24.0, 29.0), 0.40, 0.30, 1005.0,
    ),
    "bahrain": TrackProfile(
        "bahrain", 57, 5412.0, 92.5, 325.0,
        ((660, 75), (790, 120), (1250, 210), (1820, 85), (2150, 160),
         (2450, 180), (2850, 75), (3180, 95), (3700, 145), (4130, 185),
         (4620, 120), (4980, 110)),
        ((0, 600), (1300, 1780), (5050, 5412)),
        23.5, (24.0, 28.0), 0.35, 0.30, 1009.0,
    ),
    "generic": TrackProfile(
        "generic", 58, 5200.0, 89.0, 330.0,
        ((700, 90), (1100, 150), (1700, 120), (2300, 190), (2900, 100),
         (3400, 140), (3900, 170), (4500, 85), (4900, 130)),
        ((0, 650), (2400, 2850)),
        22.0, (20.0, 28.0), 0.40, 0.30, 1010.0,
    ),
}

EVENTS_2024 = [
    ("Bahrain Grand Prix", "Sakhir", "Bahrain", "2024-03-02"),
    ("Saudi Arabian Grand Prix", "Jeddah", "Saudi Arabia", "2024-03-09"),
    ("Australian Grand Prix", "Melbourne", "Australia", "2024-03-24"),
    ("Japanese Grand Prix", "Suzuka", "Japan", "2024-04-07"),
    ("Chinese Grand Prix", "Shanghai", "China", "2024-04-21"),
    ("Miami Grand Prix", "Miami", "United States", "2024-05-05"),
    ("Emilia Romagna Grand Prix", "Imola", "Italy", "2024-05-19"),
    ("Monaco Grand Prix", "Monaco", "Monaco", "2024-05-26"),
    ("Canadian Grand Prix", "Montréal", "Canada", "2024-06-09"),
    ("Spanish Grand Prix", "Barcelona", "Spain", "2024-06-23"),
    ("Austrian Grand Prix", "Spielberg", "Austria", "2024-06-30"),
    ("British Grand Prix", "Silverstone", "United Kingdom", "2024-07-07"),
    ("Hungarian Grand Prix", "Budapest", "Hungary", "2024-07-21"),
    ("Belgian Grand Prix", "Spa-Francorchamps", "Belgium", "2024-07-28"),
    ("Dutch Grand Prix", "Zandvoort", "Netherlands", "2024-08-25"),
    ("Italian Grand Prix", "Monza", "Italy", "2024-09-01"),
    ("Azerbaijan Grand Prix", "Baku", "Azerbaijan", "2024-09-15"),
    ("Singapore Grand Prix", "Marina Bay", "Singapore", "2024-09-22"),
    ("United States Grand Prix", "Austin", "United States", "2024-10-20"),
    ("Mexico City Grand Prix", "Mexico City", "Mexico", "2024-10-27"),
    ("São Paulo Grand Prix", "São Paulo", "Brazil", "2024-11-03"),
    ("Las Vegas Grand Prix", "Las Vegas", "United States", "2024-11-23"),
    ("Qatar Grand Prix", "Lusail", "Qatar", "2024-12-01"),
    ("Abu Dhabi Grand Prix", "Yas Island", "United Arab Emirates", "2024-12-08"),
]

CONVENTIONAL = ["Practice 1", "Practice 2", "Practice 3", "Qualifying", "Race"]
SESSION_OFFSETS_H = {
    "Practice 1": -48.0, "Practice 2": -44.0, "Practice 3": -24.5,
    "Qualifying": -21.0, "Race": 0.0,
}


def schedule(year):
    rows = []
    shift = pd.DateOffset(years=int(year) - 2024)
    for i, (name, loc, country, date) in enumerate(EVENTS_2024, start=1):
        race = pd.Timestamp(date) + shift + pd.Timedelta(hours=14)
        row = {
            "RoundNumber": i,
            "EventName": name,
            "Location": loc,
            "Country": country,
            "EventFormat": "conventional",
            "EventDate": race.normalize(),
        }
        for j, s in enumerate(CONVENTIONAL, start=1):
            row[f"Session{j}"] = s
            row[f"Session{j}DateUtc"] = race + pd.Timedelta(hours=SESSION_OFFSETS_H[s])
        rows.append(row)
    return pd.DataFrame(rows)


def resolve_event(year, gp):
    sched = schedule(year)
    if isinstance(gp, (int,)) or (isinstance(gp, str) and gp.isdigit()):
        hit = sched[sched["RoundNumber"] == int(gp)]
    else:
        needle = str(gp).lower()
        mask = (
            sched["EventName"].str.lower().str.contains(needle, regex=False)
            | sched["Location"].str.lower().str.contains(needle, regex=False)
            | sched["Country"].str.lower().str.contains(needle, regex=False)
        )
        hit = sched[mask]
    if hit.empty:
        raise LookupError(f"No event matching {gp!r} in {year}")
    return hit.iloc[0]


def track_for(event):
    text = f"{event['EventName']} {event['Location']} {event['Country']}".lower()
    for key, words in TRACK_KEYWORDS.items():
        if any(w in text for w in words):
            return TRACKS[key]
    return TRACKS["generic"]


TRACK_KEYWORDS = {
    "mexico": ("mexico",),
    "spa": ("belgian", "spa-francorchamps"),
    "monza": ("monza", "italian grand prix"),
    "bahrain": ("bahrain", "sakhir"),
}
