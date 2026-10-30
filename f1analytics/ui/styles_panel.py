import streamlit as st

from f1analytics.pitwall import racecraft as rc
from f1analytics.pitwall.engine import start_tyre_options
from f1analytics.ui import glossary as gl

BARS = [
    ("attack_score", "Attack", "How often he gets the pass done after closing to within a second."),
    ("defence_score", "Defence", "How often he keeps the place when a car is within a second behind."),
    ("starts_score", "Starts", "Places gained on lap 1."),
    ("tyres_score", "Tyre care", "How slowly his tyres wear compared with the field."),
    ("pace_score", "Race pace", "Lap speed over a full race, fuel effect removed."),
    ("braking_score", "Late braking", "How late he hits the brakes into the big stops."),
    ("straights_score", "Straights", "How hard the car keeps pulling late on the straights (battery deployment)."),
]

CSS = """
<style>
.sty-card{background:var(--asphalt);border-radius:6px;padding:.8rem 1rem;border-top:4px solid var(--team);height:100%}
.sty-name{font-family:var(--display) !important;font-stretch:125%;font-variation-settings:'wdth' 125;font-weight:800;font-style:italic;font-size:1.35rem;line-height:1}
.sty-team{color:var(--tarmac);font-size:.85rem;margin-bottom:.5rem}
.sty-tag{display:inline-block;background:color-mix(in srgb,var(--team) 30%,transparent);border-radius:3px;padding:1px 8px;margin:0 4px 4px 0;font-weight:700;font-size:.8rem}
.sty-row{display:grid;grid-template-columns:7.5rem 1fr 2.4rem;align-items:center;gap:.5rem;margin:.32rem 0;font-size:.88rem}
.sty-bar{height:8px;border-radius:4px;background:#2E2E3A;overflow:hidden}
.sty-bar>span{display:block;height:100%;background:var(--team)}
.sty-n{text-align:right;font-variant-numeric:tabular-nums;color:var(--tarmac)}
.sty-facts{color:var(--tarmac);font-size:.82rem;margin-top:.5rem;line-height:1.45}
.sty-here{margin-top:.6rem;padding:.35rem .6rem;border-radius:4px;background:color-mix(in srgb,var(--team) 18%,transparent);font-weight:600;font-size:.88rem}
.sty-verdict{background:var(--asphalt);border-radius:6px;padding:1rem 1.1rem;margin:.6rem 0}
.sty-big{font-family:var(--display) !important;font-stretch:125%;font-variation-settings:'wdth' 125;font-weight:800;font-style:italic;font-size:2.4rem;line-height:1}
.sty-split{display:flex;height:12px;border-radius:6px;overflow:hidden;margin:.6rem 0 .4rem}
.sty-tyre{display:grid;grid-template-columns:2rem 1fr auto;gap:.6rem;align-items:center;background:var(--asphalt);border-radius:4px;padding:.5rem .7rem;margin:.3rem 0}
.sty-tyre.best{box-shadow:inset 3px 0 0 #00B050}
@media (max-width:640px){.sty-row{grid-template-columns:6.2rem 1fr 2.2rem}.sty-big{font-size:1.9rem}}
</style>
"""


@st.cache_data(ttl=3600, show_spinner=False)
def season(year=2026):
    return rc.load(year)


@st.cache_data(ttl=3600, show_spinner=False)
def affinity():
    hist = rc.load_history()
    return rc.track_affinity(hist["rows"]) if hist else {}


def _track_line(t):
    fin = ", ".join(("DNF" if f is None else f"P{f}") + f" '{str(y)[2:]}" for f, y in zip(t["finishes"], t["years"]))
    return f"{t['location'].replace(' Circuit', '')} ({fin})"


def _tracks_html(code, track):
    aff = affinity()
    a = aff.get(code)
    if not a:
        return ""
    best = " · ".join(_track_line(t) for t in a["best"])
    worst = " · ".join(_track_line(t) for t in a["worst"])
    here = rc.affinity_at(aff, code, track) if track else None
    out = ""
    if here:
        word = "a strong track for him" if here["score"] <= -0.15 else ("one of his tougher tracks" if here["score"] >= 0.15 else "about his normal level")
        out += f"<div class='sty-here'>At {track}: {word} ({_track_line(here)})</div>"
    out += f"<div class='sty-facts'><b>Strongest tracks:</b> {best or '—'}<br><b>Bogey tracks</b> (furthest off his usual level): {worst or '—'}</div>"
    return out


def _colour(snap, code):
    d = next((x for x in (snap or {}).get("drivers", []) if x.get("code") == code), None)
    return (d or {}).get("colour") or "#888"


def _facts(p):
    out = []
    def mate(key, unit, fmt="{:+.0f}"):
        v = p.get(f"{key}_vs_mate")
        return f" ({fmt.format(v)} {unit} vs {p['teammate']}, same car)" if v is not None and p.get("teammate") else ""
    if p.get("brake_later_m") is not None:
        v = p["brake_later_m"]
        out.append(f"Brakes {abs(v):.0f} m {'later' if v > 0 else 'earlier'} than the average driver into big stops{mate('brake_later_m', 'm')}.")
    if p.get("late_straight_acc") is not None:
        v = p["late_straight_acc"]
        out.append(f"Late on the straights the car {'keeps accelerating harder' if v > 0 else 'pulls less hard'} than average ({v:+.2f} km/h per second){mate('late_straight_acc', 'km/h/s', '{:+.2f}')}.")
    if p.get("top_speed_kmh") is not None:
        out.append(f"Top speed {p['top_speed_kmh']:+.1f} km/h vs the field (mostly the car).")
    out.append(f"On-track passes: {p['passes_made']} made, {p['passes_lost']} lost in {p['races']} races (pit stops, lap 1 and Safety Cars left out).")
    if p.get("lap1_gain") is not None:
        out.append(f"Lap 1: usually {p['lap1_gain']:+.0f} places.")
    return out


def driver_style_card(snap, p, colour, track=None):
    tags = "".join(f"<span class='sty-tag' title='{t['why']}'>{t['name']}</span>" for t in p.get("tags", [])) or "<span class='pw-sub'>No standout trait yet</span>"
    rows = []
    for key, label, _ in BARS:
        v = p.get(key)
        rows.append(f"<div class='sty-row'><span>{label}</span><div class='sty-bar'><span style='width:{v or 0}%'></span></div><span class='sty-n'>{'' if v is None else v}</span></div>")
    facts = "<br>".join(_facts(p))
    st.markdown(
        f"<div class='sty-card' style='--team:{colour}'><div class='sty-name'>{p['code']}</div><div class='sty-team'>{p.get('team') or ''} · {p['races']} races</div>"
        f"<div>{tags}</div>{''.join(rows)}<div class='sty-facts'>{facts}</div>{_tracks_html(p['code'], track)}</div>",
        unsafe_allow_html=True,
    )


def _default_rival(snap, focus, codes):
    order = sorted([d for d in (snap or {}).get("drivers", []) if d.get("position") and d.get("code") in codes], key=lambda d: d["position"])
    names = [d["code"] for d in order]
    if focus in names:
        i = names.index(focus)
        if i > 0:
            return names[i - 1]
        if len(names) > 1:
            return names[1]
    if focus == "HAM" and "VER" in codes:
        return "VER"
    return next((c for c in codes if c != focus), None)


def styles_section(snap, focus):
    data = season()
    st.markdown(CSS, unsafe_allow_html=True)
    st.subheader("Driving styles and head to head")
    if not data or not data.get("profiles"):
        st.caption("Driver style data isn't built yet. Run `python -m f1analytics styles build` once.")
        return
    profiles = data["profiles"]
    codes = sorted(c for c, p in profiles.items() if p["races"] >= rc.MIN_RACES)
    if focus not in profiles:
        st.caption(f"No season data for {focus} yet.")
        return
    rival_default = _default_rival(snap, focus, codes)
    key = f"sty_rival_{focus}"
    if st.session_state.get(key) not in codes:
        st.session_state[key] = rival_default
    rival = st.selectbox(f"Can {focus} beat…", [c for c in codes if c != focus], key=key)
    gl.plain("Scores are 0–100: 50 is an average driver this season, 90 means better than 9 in 10. Braking and straights come from car telemetry on clean laps in clear air; the 'vs teammate' numbers show what's the driver rather than the car.")
    h2h = rc.head_to_head(snap, profiles, focus, rival)
    if h2h:
        a_col, b_col = _colour(snap, focus), _colour(snap, rival)
        if a_col.lower() == b_col.lower():
            b_col = "#9A9AA8"
        pa = round(h2h["prob"] * 100)
        when = "today, from the live race so far" if h2h["source"] == "today" else "on season form (updates once the race is running)"
        st.markdown(
            f"<div class='sty-verdict'><div class='pw-sub'>Chance {focus} finishes ahead of {rival} {when}</div>"
            f"<div class='sty-big'>{focus} {pa}%</div>"
            f"<div class='sty-split'><span style='width:{pa}%;background:{a_col}'></span><span style='width:{100 - pa}%;background:{b_col}'></span></div>"
            f"<div class='pw-sub'>{rival} {100 - pa}% · on pace and strategy alone {focus} {round(h2h['pace_only'] * 100)}%</div>"
            f"<ul style='margin:.5rem 0 0 1rem;padding:0'>{''.join(f'<li>{r}</li>' for r in h2h['reasons'])}</ul></div>",
            unsafe_allow_html=True,
        )
    track = ((snap or {}).get("session") or {}).get("circuit")
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        driver_style_card(snap, profiles[focus], _colour(snap, focus), track)
    with c2:
        driver_style_card(snap, profiles[rival], _colour(snap, rival), track)
    grid_comparison(snap, data, focus, rival)
    gl.words("styles", "Driver-style words explained")
    with st.expander("How the styles are worked out"):
        st.markdown(
            f"- From {len({r['session_key'] for r in data.get('rows', [])})} races this season (OpenF1 data), built {str(data.get('built', ''))[:10]}.\n"
            "- **Attack / defence:** on-track passes only. Passes on lap 1, under Safety Car, or while either car is pitting are left out. "
            "Attack = passes made per lap spent within 1 s of the car ahead; defence = places kept per lap with a car within 1 s behind. Small samples are pulled towards the average.\n"
            "- **Braking / straights:** each driver's fastest clean lap in clear air (2 s+ gap) per race. Brake points are compared corner by corner with the field.\n"
            "- **Strongest / bogey tracks:** every race since 2023. At each track, race pace is compared with the driver's own usual pace that season and with his teammate's, so a fast car doesn't make every track look good. Tracks with 2+ visits are preferred; results in brackets are finishing positions by year.\n"
            "- **Chance to finish ahead:** today's gap, each car's best strategy from the pit-wall model and recent pace, run 4,000 times with random noise; "
            "if the faster car has to pass on track it only gets by as often as its attack and the other's defence suggest.\n"
            "- All numbers are estimates from public timing data; the car matters as much as the driver."
        )


def start_tyres_section(snap):
    data = season()
    stats = (data or {}).get("start_tyres") or {}
    try:
        res = start_tyre_options(snap)
    except Exception:
        return
    if not res["options"]:
        return
    from f1analytics.ui.pitwall_page import tyre_dot

    st.subheader("Best tyre to start on")
    best = res["options"][0]["total"]
    for o in res["options"]:
        plan = " → ".join([o["compound"].title()] + [f"{c.title()} (lap {l})" for c, l in zip(o["next"], o["pit_laps"])])
        gap = "fastest" if o["delta"] < 0.05 else f"+{o['delta']:.1f}s"
        s = stats.get(o["compound"])
        g = round(s["lap1_gain"], 1) if s else 0
        hist = (f" · lap 1 this season: {'no change on average' if g == 0 else f'{g:+.1f} places on average'} ({s['starts']} starts)") if s else ""
        st.markdown(
            f"<div class='sty-tyre {'best' if o['total'] - best < 0.05 else ''}'>{tyre_dot(o['compound'])}"
            f"<div><b>{plan}</b><div class='pw-sub'>{o['stops']} stop{'s' if o['stops'] != 1 else ''}{hist}</div></div><div class='pw-v'>{gap}</div></div>",
            unsafe_allow_html=True,
        )
    gl.plain(f"Each line is the fastest {res['laps']}-lap race plan that starts on that tyre, with a pit stop costing ~{res['pit_loss']:.0f}s. "
             "Softs are quicker off the line but wear out sooner; the time shown is the whole race. Tyre wear comes from this weekend's laps when there are enough, otherwise season defaults.")


QUADRANTS = [(75, 92, "Hunters and walls"), (25, 92, "Hunters"), (75, 8, "Walls"), (25, 8, "Quiet racers")]


def grid_comparison(snap, data, focus, rival):
    import pandas as pd
    import plotly.graph_objects as go

    from f1analytics.ui.pitwall_page import _font

    profiles = data["profiles"]
    pool = [p for p in profiles.values() if p.get("attack_score") is not None and p.get("defence_score") is not None]
    if not pool:
        return
    st.subheader("Grid comparison: attack, defence and podiums")
    colours = {d.get("code"): d.get("colour") for d in (snap or {}).get("drivers", [])}
    fig = go.Figure()
    for x, y, name in QUADRANTS:
        fig.add_annotation(x=x, y=y, text=name, showarrow=False, font=dict(size=11, color="#6B6B7A"))
    fig.add_shape(type="line", x0=50, x1=50, y0=0, y1=100, line=dict(color="#2E2E3A", width=1))
    fig.add_shape(type="line", x0=0, x1=100, y0=50, y1=50, line=dict(color="#2E2E3A", width=1))
    key = {focus, rival}
    fig.add_trace(go.Scatter(
        x=[p["defence_score"] for p in pool], y=[p["attack_score"] for p in pool], mode="markers+text",
        text=[p["code"] for p in pool], textposition="top center",
        textfont=dict(size=[13 if p["code"] in key else 10 for p in pool], color=["#F3F3F5" if p["code"] in key else "#9A9AA8" for p in pool]),
        marker=dict(size=[18 if p["code"] in key else 11 for p in pool], color=[colours.get(p["code"]) or "#777" for p in pool], line=dict(width=1.5, color="#15151E")),
        hovertext=[f"{p['code']}: attack {p['attack_score']}, defence {p['defence_score']}" for p in pool], hoverinfo="text"))
    fig.update_xaxes(title="Defence (holds position under pressure) →", range=[-3, 103], showgrid=False, zeroline=False)
    fig.update_yaxes(title="Attack (gets passes done) →", range=[-3, 103], showgrid=False, zeroline=False)
    fig.update_layout(height=430, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    c1, c2 = st.columns([3, 2], gap="medium")
    with c1:
        st.plotly_chart(_font(fig), key=f"grid_scatter_{focus}_{rival}", config={"displayModeBar": False})
    with c2:
        table = rc.podium_table(data.get("rows", []))
        if not table.empty:
            show = table.head(12).copy()
            show["Driver"] = show["code"].map(lambda c: f"⭐ {c}" if c in key else c)
            show = show.rename(columns={"wins": "Wins", "podiums": "Podiums", "gained": "Places gained", "beat_mate": "Beat teammate %"})
            show["Beat teammate %"] = show["Beat teammate %"].round(0)
            st.dataframe(show[["Driver", "Wins", "Podiums", "Places gained", "Beat teammate %"]].round(1), hide_index=True, width="stretch")
    gl.plain("Top right are drivers who both make passes stick and are hard to pass. 'Places gained' is grid to chequered flag on average; "
             "'Beat teammate %' is how often he finishes ahead of the driver in the same car, the fairest way to see who gets more out of it "
             "and turns it into podiums.")
