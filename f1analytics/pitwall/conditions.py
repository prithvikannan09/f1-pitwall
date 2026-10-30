import math

SEA_LEVEL_DENSITY = 1.225
R_DRY = 287.05
R_VAPOUR = 461.5


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def air_density(pressure_hpa, temp_c, humidity_pct=0.0):
    p, t, h = _num(pressure_hpa), _num(temp_c), _num(humidity_pct) or 0.0
    if p is None or t is None or p <= 0:
        return None
    sat = 6.1078 * 10 ** (7.5 * t / (t + 237.3))
    pv = sat * h / 100.0
    pd_ = p - pv
    tk = t + 273.15
    return (pd_ * 100) / (R_DRY * tk) + (pv * 100) / (R_VAPOUR * tk)


def altitude_from_pressure(pressure_hpa):
    p = _num(pressure_hpa)
    if p is None or p <= 0:
        return None
    return 44330.0 * (1 - (p / 1013.25) ** 0.1903)


def analyse(weather):
    w = weather or {}
    air, track, hum = _num(w.get("AirTemp")), _num(w.get("TrackTemp")), _num(w.get("Humidity"))
    wind, rain, press = _num(w.get("WindSpeed")), _num(w.get("Rainfall")), _num(w.get("Pressure"))
    rho = air_density(press, air, hum)
    out = {"air": air, "track": track, "humidity": hum, "wind": wind, "rain": bool(rain), "pressure": press,
           "density": rho, "thinner_pct": None, "altitude_m": None, "effects": []}
    fx = out["effects"]
    if rho:
        thin = (1 - rho / SEA_LEVEL_DENSITY) * 100
        out["thinner_pct"] = thin
        out["altitude_m"] = altitude_from_pressure(press)
        if thin >= 12:
            fx.append(("Less grip in corners", f"Wings and floor make about {thin:.0f}% less downforce in air this thin, so even with the biggest wings the cars slide more and brake earlier."))
            fx.append(("Faster on the straights", f"Drag also drops about {thin:.0f}%, so top speeds are higher than the wing level suggests and a slipstream on the long straights counts for more."))
            fx.append(("Hard to keep cool", "Thin air carries away less heat, so brakes, engine and battery run hot. Teams open up bodywork, which costs some speed, and following another car makes it worse."))
            fx.append(("Turbo working overtime", "The turbo has to squeeze much more air into the engine to make normal power, which stresses it and makes engine settings and battery use more critical."))
        elif thin >= 4:
            fx.append(("Slightly thin air", f"About {thin:.0f}% thinner than at sea level: a little less downforce and drag, and a bit harder to cool the car."))
        else:
            fx.append(("Normal air", "Close to sea-level air density, so no altitude effect on grip, drag or cooling."))
    if track is not None:
        if track >= 45:
            fx.append(("Hot track", f"{track:.0f}°C track: tyres overheat and wear faster, so drivers have to manage them and stops may come earlier."))
        elif track <= 25:
            fx.append(("Cool track", f"{track:.0f}°C track: tyres take longer to warm up and can grain (tear on the surface), especially the harder ones."))
        else:
            fx.append(("Track in the sweet spot", f"{track:.0f}°C track: tyres should work in their normal window."))
    if wind is not None and wind >= 5:
        fx.append(("Windy", f"{wind:.0f} m/s wind: gusts can unsettle the car in fast corners and change top speeds depending on direction."))
    if out["rain"]:
        fx.append(("Rain", "Wet track: expect intermediate or wet tyres, lower grip and more mistakes."))
    return out


def weather_kind(c):
    if c.get("rain"):
        return "wet", "Wet"
    track, air = c.get("track"), c.get("air")
    if (track is not None and track >= 45) or (air is not None and air >= 30):
        return "hot", "Hot and dry"
    if air is not None and air <= 15:
        return "cool", "Cool and dry"
    if air is None and track is None:
        return None, ""
    return "mild", "Dry"


THEMES = {
    "wet": ("radial-gradient(ellipse 120% 70% at 50% -10%, rgba(70,110,170,0.28), transparent 65%), #12161E",
            "repeating-linear-gradient(105deg, rgba(160,190,230,0.10) 0 1px, transparent 1px 22px)"),
    "hot": ("radial-gradient(ellipse 110% 60% at 50% -12%, rgba(255,128,32,0.20), transparent 62%), #17141A", None),
    "cool": ("radial-gradient(ellipse 110% 60% at 50% -12%, rgba(90,170,255,0.16), transparent 62%), #12151D", None),
    "mild": ("radial-gradient(ellipse 110% 55% at 50% -12%, rgba(255,214,140,0.10), transparent 60%), #15151E", None),
}


def theme_css(kind):
    if kind not in THEMES:
        return ""
    bg, rain = THEMES[kind]
    css = f".stApp{{background:{bg} !important;background-attachment:fixed !important;transition:background .8s ease}}"
    if rain:
        css += (f".stApp::before{{content:'';position:fixed;inset:-50% 0 0 0;pointer-events:none;z-index:0;background:{rain};"
                "animation:pw-rain .9s linear infinite;opacity:.9}}"
                ".stApp > *{{position:relative;z-index:1}}"
                "@keyframes pw-rain{from{transform:translateY(0)}to{transform:translateY(22px)}}"
                "@media (prefers-reduced-motion:reduce){.stApp::before{animation:none}}")
    return f"<style>{css}</style>"
