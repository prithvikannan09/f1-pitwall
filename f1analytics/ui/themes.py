import random
from datetime import datetime, timedelta, timezone

import pandas as pd

TEAM_GROUND = {
    "ferrari": "#170A0C", "red bull": "#0A1022", "mercedes": "#061412", "mclaren": "#150C04", "aston": "#06130E",
    "racing bulls": "#0A0E1D", "rb ": "#0A0E1D", "haas": "#101112", "alpine": "#06101A", "williams": "#060D1C",
    "audi": "#130A0C", "sauber": "#06130A", "cadillac": "#0F0F10",
}
DEFAULT_GROUND = "#15151E"

HELMETS = {
    "HAM": ("#FFCC00", "#E8002D", "Modena yellow, Ferrari red"),
    "LEC": ("#E10531", "#7EC8F2", "Red and white, light blue"),
    "VER": ("#E8343F", "#2F5BB7", "Dutch red, white and blue"),
    "HAD": ("#FFD400", "#7B3FD1", "Yellow, purple and black"),
    "ANT": ("#13A85A", "#E03A44", "Italian green, white and red"),
    "RUS": ("#5BC3F5", "#0B0B0B", "Sky blue and black"),
    "NOR": ("#D4FF2A", "#111111", "Neon yellow-green and black"),
    "PIA": ("#E4002B", "#FFCD00", "Red, yellow and blue"),
    "ALO": ("#3DA9E0", "#FFD100", "Asturian blue, yellow and red"),
    "STR": ("#9AA0A6", "#2B2B2B", "Black and dark grey"),
    "LIN": ("#39FF6A", "#2E6BFF", "Neon green, blue and red"),
    "LAW": ("#FF5FA2", "#F5F5F5", "White and pink"),
    "BEA": ("#3A78F2", "#CCFF00", "Blue with neon and white"),
    "OCO": ("#E10600", "#FFFFFF", "Red"),
    "GAS": ("#2B5BE0", "#E1251B", "Blue with a French tricolour"),
    "COL": ("#74ACDF", "#E1251B", "Argentine flag, black and red"),
    "SAI": ("#E3262B", "#FFD100", "Red and yellow, Williams blue"),
    "ALB": ("#E8EAEE", "#1F5FD6", "Chrome white, Williams blue"),
    "HUL": ("#C9CCD1", "#FF7A1A", "Silver grey and orange"),
    "BOR": ("#1FA34A", "#FFD400", "Brazilian green and yellow"),
    "PER": ("#7CFF3A", "#CE1126", "Neon green, Mexican flag"),
    "BOT": ("#2A64C8", "#9AA0A6", "Black, blue and grey"),
}

NIGHT_TRACKS = ("las vegas", "marina bay", "singapore", "lusail", "qatar", "yas", "abu dhabi", "sakhir", "bahrain", "jeddah")
SKY = {
    "day": {"dry": "linear-gradient(180deg,rgba(96,150,220,.22),rgba(96,150,220,.05) 30%,transparent 55%)",
            "hot": "linear-gradient(180deg,rgba(240,170,90,.24),rgba(240,170,90,.06) 32%,transparent 58%)",
            "rain": "linear-gradient(180deg,rgba(150,162,182,.26),rgba(120,135,160,.08) 38%,transparent 64%)"},
    "dusk": {"dry": "linear-gradient(180deg,rgba(70,50,120,.32),rgba(230,110,90,.18) 26%,rgba(255,160,90,.07) 46%,transparent 66%)",
             "hot": "linear-gradient(180deg,rgba(90,50,100,.3),rgba(255,130,60,.2) 26%,transparent 60%)",
             "rain": "linear-gradient(180deg,rgba(80,70,110,.32),rgba(170,110,120,.13) 34%,transparent 62%)"},
    "night": {"dry": "linear-gradient(180deg,rgba(34,48,96,.42),rgba(40,56,110,.12) 36%,transparent 64%)",
              "hot": "linear-gradient(180deg,rgba(60,40,70,.42),rgba(90,50,40,.12) 36%,transparent 64%)",
              "rain": "linear-gradient(180deg,rgba(40,54,88,.46),rgba(46,60,96,.16) 40%,transparent 66%)"},
}


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def mix(a, b, t):
    x, y = _rgb(a), _rgb(b)
    return "#" + "".join(f"{round(p + (q - p) * t):02x}" for p, q in zip(x, y))


def is_light(h):
    r, g, b = _rgb(h)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6


def readable(h):
    r, g, b = _rgb(h)
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return h if lum >= 0.42 else mix(h, "#FFFFFF", 0.45)


def ground_for(team):
    t = str(team or "").lower()
    return next((g for k, g in TEAM_GROUND.items() if k in t), DEFAULT_GROUND)


def helmet(code, team_colour=None):
    lead, second, desc = HELMETS.get(str(code or "").upper(), (team_colour or "#E10600", "#FFFFFF", ""))
    return {"lead": lead, "second": second, "desc": desc, "text": readable(lead), "ink": "#15151E" if is_light(lead) else "#FFFFFF"}


def _offset(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    try:
        neg = s.startswith("-")
        parts = [int(p) for p in s.lstrip("+-").split(":")[:2]]
        d = timedelta(hours=parts[0], minutes=parts[1] if len(parts) > 1 else 0)
        return -d if neg else d
    except (ValueError, IndexError):
        return None


def time_of_day(snap, now=None):
    snap = snap or {}
    s = snap.get("session") or {}
    off = _offset(snap.get("gmt_offset") or s.get("gmt_offset"))
    if off is not None:
        t = pd.Timestamp(snap.get("now_utc")) if snap.get("now_utc") else pd.Timestamp(now or datetime.now(timezone.utc))
        if t.tzinfo is not None:
            t = t.tz_convert(None)
        hour = (t + off).hour + (t + off).minute / 60
        if hour >= 19 or hour < 6:
            return "night"
        if hour >= 17:
            return "dusk"
        return "day"
    place = f"{s.get('circuit') or ''} {s.get('meeting') or ''}".lower()
    return "night" if any(k in place for k in NIGHT_TRACKS) else "day"


def _drops(n_far, n_mid, n_near, seed=44):
    rnd = random.Random(seed)
    out = []
    for n, h0, h1, o0, o1, d0, d1, w, blur in ((n_far, 8, 16, .14, .26, 1.05, 1.45, 1, 0), (n_mid, 16, 30, .22, .4, .68, .9, 1, 0), (n_near, 44, 78, .28, .5, .4, .52, 1.5, .6)):
        for _ in range(n):
            d = d0 + rnd.random() * (d1 - d0)
            out.append(f"<i class='pwx-drop' style='left:{rnd.random() * 100:.2f}%;width:{w}px;height:{round(h0 + rnd.random() * (h1 - h0))}px;"
                       f"opacity:{o0 + rnd.random() * (o1 - o0):.2f};animation-duration:{d:.2f}s;animation-delay:-{rnd.random() * d * 3:.2f}s"
                       + (f";filter:blur({blur}px)" if blur else "") + "'></i>")
    return "".join(out)


def _bits(cls, n, seed, fn):
    rnd = random.Random(seed)
    return "".join(f"<i class='{cls}' style='{fn(rnd)}'></i>" for _ in range(n))


CSS = """
.pwx{position:fixed;inset:0;pointer-events:none;z-index:-1;overflow:hidden}
.pwx>*{position:absolute;pointer-events:none}
.stApp>header,.stApp [data-testid="stAppViewContainer"]>*{position:relative;z-index:1}
.pwx-sky,.pwx-weave,.pwx-dusk,.pwx-wash,.pwx-mist,.pwx-sheen,.pwx-haze{inset:0}
.pwx-weave{background-image:repeating-linear-gradient(45deg,rgba(255,255,255,.022) 0 2px,transparent 2px 7px),repeating-linear-gradient(-45deg,rgba(255,255,255,.016) 0 2px,transparent 2px 7px)}
.pwx-field{top:-6%;left:-12%;right:-12%;bottom:0;transform:rotate(8deg);transform-origin:50% 0;animation:pwx-gust 9s ease-in-out infinite}
.pwx-field.lit{filter:brightness(1.7)}
.pwx-drop{position:absolute;top:-90px;border-radius:1px;background:linear-gradient(180deg,rgba(205,222,245,0),rgba(214,228,248,.85));animation:pwx-drop linear infinite}
.pwx-mist{background:radial-gradient(ellipse 55% 35% at 25% 78%,rgba(150,172,205,.13),transparent 70%),radial-gradient(ellipse 45% 30% at 78% 62%,rgba(150,172,205,.10),transparent 70%);animation:pwx-drift 36s ease-in-out infinite alternate}
.pwx-haze{bottom:auto;height:240px;background:linear-gradient(180deg,rgba(255,140,40,.16),transparent);animation:pwx-shim 3.2s ease-in-out infinite alternate;transform-origin:top}
.pwx-heat{bottom:-80px;border-radius:50%;background:radial-gradient(ellipse at center,rgba(255,150,60,.16),transparent 70%);filter:blur(8px);animation:pwx-rise ease-in infinite}
.pwx-glare{top:-180px;right:-160px;width:560px;height:560px;border-radius:50%;background:radial-gradient(circle,rgba(255,196,110,.18),rgba(255,160,60,.05) 45%,transparent 70%);animation:pwx-glare 6s ease-in-out infinite alternate}
.pwx-sheen{background:linear-gradient(105deg,transparent 38%,rgba(255,250,235,.03) 46%,rgba(255,250,235,.065) 50%,rgba(255,250,235,.03) 54%,transparent 62%);background-size:260% 100%;animation:pwx-sweep 12s ease-in-out infinite}
.pwx-mote{border-radius:50%;background:rgba(255,238,205,.55);animation:pwx-mote linear infinite}
.pwx-dusk{background:radial-gradient(ellipse 85% 50% at 12% 108%,rgba(255,138,64,.26),rgba(214,84,120,.1) 45%,transparent 72%);animation:pwx-breathe 10s ease-in-out infinite alternate}
.pwx-wash{background:linear-gradient(180deg,rgba(228,236,255,.13),rgba(228,236,255,.05) 40%,rgba(228,236,255,.06) 80%,rgba(255,196,130,.1))}
.pwx-rigv{top:-10px;bottom:-10px;width:24px;background-image:radial-gradient(circle,rgba(255,255,248,.95) 0 1.6px,rgba(255,252,236,.4) 3px,rgba(255,252,236,.12) 6px,transparent 9px);background-size:24px 30px;background-repeat:repeat-y;animation:pwx-twinkle 4s ease-in-out infinite alternate}
.pwx-bloomv{top:0;bottom:0;width:140px}
@keyframes pwx-drop{to{transform:translate3d(0,1600px,0)}}
@keyframes pwx-gust{0%,100%{opacity:.7}38%{opacity:1}55%{opacity:.82}72%{opacity:.95}}
@keyframes pwx-drift{from{transform:translateX(-7%)}to{transform:translateX(7%)}}
@keyframes pwx-shim{from{transform:scaleY(1);opacity:.85}to{transform:scaleY(1.12);opacity:1}}
@keyframes pwx-rise{0%{transform:translate3d(0,0,0) scale(.8,1);opacity:0}25%{opacity:1}100%{transform:translate3d(24px,-760px,0) scale(1.5,2.4);opacity:0}}
@keyframes pwx-glare{from{opacity:.65;transform:scale(1)}to{opacity:1;transform:scale(1.08)}}
@keyframes pwx-sweep{0%{background-position:125% 0}60%,100%{background-position:-25% 0}}
@keyframes pwx-mote{0%{transform:translate3d(0,0,0);opacity:0}12%{opacity:1}88%{opacity:1}100%{transform:translate3d(-320px,-46px,0);opacity:0}}
@keyframes pwx-breathe{from{opacity:.8}to{opacity:1}}
@keyframes pwx-twinkle{from{opacity:.85}to{opacity:1}}
@media (prefers-reduced-motion:reduce){.pwx *{animation:none !important}.pwx-mote,.pwx-heat{display:none}}
@media (max-width:640px){
 [data-testid="stHorizontalBlock"]:has(.pw-hero):has(.pw-tower){display:flex;flex-direction:column}
 [data-testid="stHorizontalBlock"]:has(.pw-hero):has(.pw-tower)>[data-testid="stColumn"]:nth-child(3){order:2}
 [data-testid="stHorizontalBlock"]:has(.pw-hero):has(.pw-tower)>[data-testid="stColumn"]:nth-child(2){order:3}
 .pwx-rigv{width:18px;background-size:18px 24px}
}
"""


def scene(weather, tod):
    w = weather if weather in ("dry", "hot", "rain") else "dry"
    return w, tod if tod in ("day", "dusk", "night") else "day"


def page_theme(code, team, team_colour, weather, tod):
    w, t = scene(weather, tod)
    base = ground_for(team)
    tint = {"dry": None, "hot": ("#3A1A06", .35), "rain": ("#1B2738", .55)}[w]
    g = mix(base, *tint) if tint else base
    g = mix(g, "#0B1024", .3) if t == "night" else (mix(g, "#2A1420", .32) if t == "dusk" else g)
    h = helmet(code, team_colour)
    panel = mix(g, "#FFFFFF", .06)
    alpha = "D9" if (w == "rain" or t == "night") else "F2"
    layers = [f"<div class='pwx-sky' style='background:{SKY[t][w]}'></div>", "<div class='pwx-weave'></div>"]
    if t == "dusk":
        layers.append("<div class='pwx-dusk'></div>")
    if t == "night":
        layers += ["<div class='pwx-wash'></div>",
                   "<div class='pwx-bloomv' style='left:0;background:linear-gradient(90deg,rgba(240,244,255,.12),transparent)'></div>",
                   "<div class='pwx-bloomv' style='right:0;background:linear-gradient(270deg,rgba(240,244,255,.12),transparent)'></div>",
                   "<div class='pwx-rigv' style='left:2px;opacity:.85;animation-delay:-3s'></div>",
                   "<div class='pwx-rigv' style='right:2px;opacity:.85;background-position:0 15px;animation-delay:-1.5s'></div>"]
    if w == "rain":
        layers += ["<div class='pwx-mist'></div>", f"<div class='pwx-field{' lit' if t == 'night' else ''}'>{_drops(80, 60, 22)}</div>"]
    if w == "hot":
        if t == "day":
            layers.append("<div class='pwx-glare'></div>")
        layers.append(_bits("pwx-heat", 16, 7, lambda r: (lambda d: f"left:{r.random() * 96:.1f}%;width:{round(120 + r.random() * 160)}px;height:{round(60 + r.random() * 70)}px;animation-duration:{d:.1f}s;animation-delay:-{r.random() * d:.1f}s")(7 + r.random() * 6)))
        layers.append("<div class='pwx-haze'></div>")
    if w == "dry":
        if t != "night":
            layers.append("<div class='pwx-sheen'></div>")
        layers.append(_bits("pwx-mote", 26, 3, lambda r: (lambda d, z: f"left:{10 + r.random() * 95:.1f}%;top:{r.random() * 100:.1f}%;width:{z:.1f}px;height:{z:.1f}px;animation-duration:{d:.1f}s;animation-delay:-{r.random() * d:.1f}s")(10 + r.random() * 10, 1 + r.random() * 2.2)))
    root = (f":root{{--carbon:{g};--asphalt:{panel}{alpha};--kerb:{h['lead']};--helmet:{h['lead']};--helmet-2:{h['second']};"
            f"--helmet-text:{h['text']};--helmet-ink:{h['ink']};--team-colour:{team_colour or h['lead']}}}"
            ".stApp{background:var(--carbon) !important;transition:background .8s ease}")
    return f"<style>{root}{CSS}</style><div class='pwx' aria-hidden='true'>{''.join(layers)}</div>", {"ground": g, "helmet": h, "weather": w, "time": t}


TIME_LABEL = {"day": "Afternoon", "dusk": "Golden hour", "night": "Night race"}
