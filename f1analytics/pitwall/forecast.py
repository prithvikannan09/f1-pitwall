from datetime import datetime, timezone

import pandas as pd
import requests

OPENF1 = "https://api.openf1.org/v1"
METEO = "https://api.open-meteo.com/v1/forecast"
HOURLY = "temperature_2m,precipitation_probability,precipitation,weather_code,wind_speed_10m,relative_humidity_2m,cloud_cover"

CIRCUITS = {
    "albert park": (-37.8497, 144.9680), "melbourne": (-37.8497, 144.9680),
    "shanghai": (31.3389, 121.2197),
    "suzuka": (34.8431, 136.5407),
    "sakhir": (26.0325, 50.5106), "bahrain": (26.0325, 50.5106),
    "jeddah": (21.6319, 39.1044),
    "miami": (25.9581, -80.2389),
    "montreal": (45.5000, -73.5228), "montréal": (45.5000, -73.5228),
    "monte carlo": (43.7347, 7.4206), "monaco": (43.7347, 7.4206),
    "catalunya": (41.5700, 2.2611), "barcelona": (41.5700, 2.2611),
    "madring": (40.4650, -3.6150), "madrid": (40.4650, -3.6150),
    "spielberg": (47.2197, 14.7647),
    "silverstone": (52.0786, -1.0169),
    "spa": (50.4372, 5.9714),
    "hungaroring": (47.5789, 19.2486), "budapest": (47.5789, 19.2486),
    "zandvoort": (52.3888, 4.5409),
    "monza": (45.6156, 9.2811),
    "baku": (40.3725, 49.8533),
    "singapore": (1.2914, 103.8640), "marina bay": (1.2914, 103.8640),
    "austin": (30.1328, -97.6411),
    "mexico": (19.4042, -99.0907),
    "interlagos": (-23.7036, -46.6997), "são paulo": (-23.7036, -46.6997), "sao paulo": (-23.7036, -46.6997),
    "las vegas": (36.1147, -115.1728),
    "lusail": (25.4900, 51.4542),
    "yas marina": (24.4672, 54.6031), "abu dhabi": (24.4672, 54.6031),
}

WMO = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
       51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
       80: "Showers", 81: "Heavy showers", 82: "Violent showers", 95: "Thunderstorm", 96: "Thunderstorm, hail", 99: "Thunderstorm, hail"}

RAIN_PROB = 60
SHOWER_PROB = 30
RAIN_MM = 0.5
HOT_AIR = 30


def coords(circuit, location=""):
    place = f"{circuit or ''} {location or ''}".lower()
    return next((v for k, v in CIRCUITS.items() if k in place), None)


def _get(url, params, timeout=12):
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def saved_sessions(year):
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "styles" / f"sessions_{year}.json"
    return json.loads(path.read_text()) if path.exists() else []


def weekend(now=None, year=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    try:
        rows = _get(f"{OPENF1}/sessions", {"year": year or now.year})
        if not isinstance(rows, list) or not rows:
            raise ValueError("no sessions")
    except (requests.RequestException, ValueError):
        rows = saved_sessions(year or now.year)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["start"] = pd.to_datetime(df["date_start"], utc=True)
    df["end"] = pd.to_datetime(df["date_end"], utc=True)
    nxt = df[df["end"] > now].sort_values("start")
    if nxt.empty:
        return nxt
    return nxt[nxt["meeting_key"] == nxt.iloc[0]["meeting_key"]].reset_index(drop=True)


def hourly(lat, lon, days=16):
    h = _get(METEO, {"latitude": lat, "longitude": lon, "hourly": HOURLY, "timezone": "UTC",
                     "forecast_days": days, "wind_speed_unit": "ms"})["hourly"]
    df = pd.DataFrame(h)
    df["time"] = pd.to_datetime(df["time"]).dt.tz_localize("UTC")
    return df


def summarise(hours, start, end):
    s, e = pd.Timestamp(start).floor("h"), pd.Timestamp(end).ceil("h")
    w = hours[(hours["time"] >= s) & (hours["time"] <= e)]
    if w.empty:
        return None
    code = int(w["weather_code"].max())
    out = {
        "air_min": float(w["temperature_2m"].min()), "air_max": float(w["temperature_2m"].max()),
        "rain_prob": float(w["precipitation_probability"].max()), "rain_mm": float(w["precipitation"].sum()),
        "wind": float(w["wind_speed_10m"].max()), "humidity": float(w["relative_humidity_2m"].mean()),
        "cloud": float(w["cloud_cover"].mean()), "sky": WMO.get(code, WMO.get(code - code % 10, "Mixed")),
    }
    out["kind"] = classify(out)
    return out


def classify(f):
    if f["rain_prob"] >= RAIN_PROB or f["rain_mm"] >= RAIN_MM:
        return "rain"
    if f["air_max"] >= HOT_AIR:
        return "hot"
    return "dry"


def headline(f):
    if f is None:
        return "Forecast not out yet"
    air = f"{f['air_min']:.0f}–{f['air_max']:.0f}°C" if round(f["air_min"]) != round(f["air_max"]) else f"{f['air_max']:.0f}°C"
    if f["kind"] == "rain":
        wet = f"Wet: {f['rain_prob']:.0f}% chance of rain"
    elif f["rain_prob"] >= SHOWER_PROB:
        wet = f"Dry, but {f['rain_prob']:.0f}% chance of a shower"
    elif f["kind"] == "hot":
        wet = "Hot and dry"
    else:
        wet = "Dry"
    return f"{wet} · {f['sky'].lower()} · {air}"


def weekend_forecast(now=None):
    sess = weekend(now)
    if sess.empty:
        return None
    first = sess.iloc[0]
    ll = coords(first.get("circuit_short_name"), first.get("location"))
    hours = None
    if ll:
        try:
            hours = hourly(*ll)
        except requests.RequestException:
            hours = None
    out = []
    for _, r in sess.iterrows():
        f = summarise(hours, r["start"], r["end"]) if hours is not None else None
        out.append({"session": r["session_name"], "start": r["start"].isoformat(), "end": r["end"].isoformat(),
                    "gmt_offset": r.get("gmt_offset"), "forecast": f})
    return {"meeting": f"{first.get('location')}", "circuit": first.get("circuit_short_name"),
            "country": first.get("country_name"), "gmt_offset": first.get("gmt_offset"),
            "has_coords": bool(ll), "sessions": out}


def scene_snap(wf, i=0):
    s = wf["sessions"][i]
    return {"gmt_offset": s["gmt_offset"], "now_utc": s["start"],
            "session": {"name": s["session"], "circuit": wf["circuit"], "meeting": wf["meeting"]}}
