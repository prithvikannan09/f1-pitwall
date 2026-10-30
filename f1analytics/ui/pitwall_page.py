import warnings
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import threading
import time

from f1analytics.live.recorder import LIVE_DIR, read_current, read_feed, record
from f1analytics.live.replay import RaceReplay, SessionReplay, load_fixture, load_openf1_race
from f1analytics.pitwall.car import mode_hints, practice_summary, speed_profile
from f1analytics.pitwall.engine import analyse
from f1analytics.ui import charts
from f1analytics.ui import glossary as gl

warnings.filterwarnings("ignore")

REPLAYS = Path(__file__).resolve().parent.parent / "replays"
BUNDLED = {
    "2026 US GP · Race (bundled)": ("race", REPLAYS / "usgp2026"),
    "2025 Mexico · Practice 2 (bundled)": ("practice", REPLAYS / "mex2025_fp2"),
}
RACE_TYPES = {"race", "sprint"}
CALL_STYLE = {
    "BOX THIS LAP": ("#E10600", "#FFFFFF"),
    "BOX NEXT LAP": ("#FFD12E", "#111111"),
    "STAY OUT": ("#F3F3F5", "#15151E"),
    "IN PIT": ("#5A5A68", "#FFFFFF"),
}
TYRE = {"SOFT": ("S", "#DA291C"), "MEDIUM": ("M", "#FFD12E"), "HARD": ("H", "#F0F0EC"), "INTERMEDIATE": ("I", "#43B02A"), "WET": ("W", "#0067AD")}


def tyre_dot(compound):
    letter, colour = TYRE.get(str(compound or "").upper(), ("?", "#777"))
    return f"<span class='tyre' style='--c:{colour};background:#101016;color:#F3F3F5'>{letter}</span>"


def _font(fig):
    fig.update_layout(font=dict(family="Titillium Web, sans-serif", color="#F3F3F5"), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig
STATUS_STYLE = {
    "1": ("GREEN FLAG", "#00B050"),
    "2": ("YELLOW FLAG", "#FFD12E"),
    "4": ("SAFETY CAR", "#FFD12E"),
    "5": ("RED FLAG", "#E10600"),
    "6": ("VIRTUAL SAFETY CAR", "#FFD12E"),
    "7": ("VSC ENDING", "#FFD12E"),
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Saira:ital,wdth,wght@0,50..125,100..900;1,50..125,100..900&family=Titillium+Web:wght@300;400;600;700&display=swap');
:root{--display:'Saira',sans-serif;--carbon:#15151E;--asphalt:#1F1F2B;--line:#2E2E3A;--chalk:#F3F3F5;--tarmac:#9A9AA8;--kerb:#E10600;--flag:#FFD12E;--go:#00B050}
.stApp,.stApp :is(div,p,label,input,button,li,td,th,h1,h2,h3,h4,textarea,select,small,b,strong,a,summary,table){font-family:'Titillium Web',system-ui,sans-serif !important}
.stApp [data-testid="stIconMaterial"],.stApp .material-symbols-rounded{font-family:'Material Symbols Rounded' !important}
.stApp{background:var(--carbon);color:var(--chalk)}
[data-testid="stToolbar"],[data-testid="stDecoration"]{display:none}
.block-container{max-width:1500px;padding-top:3.6rem !important}
.stApp h1,.stApp .pw-d,.stApp .pw-pos,.stApp .pw-code,.stApp .pw-call,.stApp .pw-call span,.stApp .pw-lap,.stApp .pw-flag,.stApp .pw-tower .code,.stApp .pw-tower .p,.stApp .pw-empty b{font-family:var(--display) !important;font-stretch:125%;font-variation-settings:'wdth' 125}
.stApp h3{font-family:var(--display) !important;font-stretch:112%;font-variation-settings:'wdth' 112;text-transform:none}
h1{font-weight:800 !important;font-style:italic;letter-spacing:-0.5px;font-size:2.1rem !important;padding:0 !important;margin:0 0 .6rem !important;display:flex;align-items:center;gap:.6rem}
h1::before{content:"";width:44px;height:.62em;background:var(--kerb);transform:skewX(-20deg);display:inline-block}
h3{font-weight:700 !important;font-size:1.05rem !important;letter-spacing:.2px;border-bottom:1px solid var(--line);padding:.2rem 0 .35rem !important;margin:1rem 0 .5rem !important}
h3 a{display:none !important}
.num{font-variant-numeric:tabular-nums}
.pw-strip{display:flex;flex-wrap:wrap;align-items:stretch;gap:0;margin:.2rem 0 .3rem;border-radius:4px;overflow:hidden;background:var(--asphalt)}
.pw-strip>div{padding:.5rem .9rem;display:flex;flex-direction:column;justify-content:center}
.pw-flag{color:#111;font-weight:800;font-style:italic;font-size:.85rem;min-width:120px}
.pw-lap{font-weight:800;font-style:italic;font-size:1.35rem;line-height:1}
.pw-lap small{font-weight:400;color:var(--tarmac);font-size:.95rem}
.pw-gp{font-weight:600}
.pw-gp small,.pw-loss small{display:block;color:var(--tarmac);font-weight:400;font-size:.8rem}
.pw-loss{margin-left:auto;text-align:right;font-weight:700}
.pw-feed{color:var(--tarmac);font-size:.8rem;margin:0 0 .6rem}
.pw-live-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--kerb);margin-right:6px;animation:pw-pulse 1.6s infinite}
@keyframes pw-pulse{0%,100%{opacity:1}50%{opacity:.25}}
@media (prefers-reduced-motion:reduce){.pw-live-dot{animation:none}}
.pw-follow{border-left:4px solid var(--team);padding-left:8px;color:var(--tarmac);font-size:.85rem;margin:-.2rem 0 .8rem}
.pw-hero{position:relative;background:linear-gradient(100deg,color-mix(in srgb,var(--team) 34%,var(--asphalt)) 0%,var(--asphalt) 55%);border-radius:6px;padding:.9rem 1rem .8rem;margin-bottom:.6rem;overflow:hidden}
.pw-hero::after{content:"";position:absolute;right:-30px;top:0;bottom:0;width:90px;background:var(--team);opacity:.18;transform:skewX(-20deg)}
.pw-id{display:flex;align-items:flex-end;gap:.9rem}
.pw-pos{font-weight:800;font-style:italic;font-size:3.1rem;line-height:.85;font-variant-numeric:tabular-nums}
.pw-pos small{font-size:1.4rem;opacity:.7}
.pw-code{font-weight:800;font-size:1.5rem;line-height:1;letter-spacing:.5px}
.pw-name{color:var(--tarmac);font-size:.9rem}
.pw-call{display:inline-block;margin:.8rem 0 .2rem .4rem;padding:.35rem 1.4rem .35rem 1.1rem;transform:skewX(-14deg);font-weight:800;font-style:italic;font-size:1.6rem;letter-spacing:.3px;box-shadow:-8px 0 0 var(--team)}
.pw-call>span{display:inline-block;transform:skewX(14deg)}
.pw-why{color:var(--chalk);opacity:.85;font-size:.95rem;margin-top:.35rem}
.pw-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:2px;margin:.2rem 0 .9rem;background:var(--line);border-radius:4px;overflow:hidden}
.pw-grid>div{background:var(--asphalt);padding:.45rem .6rem}
.pw-k{color:var(--tarmac);font-size:.78rem}
.pw-v{font-size:1.15rem;font-weight:700;white-space:nowrap;font-variant-numeric:tabular-nums;display:flex;align-items:center;gap:.35rem}
.tyre{display:inline-flex;align-items:center;justify-content:center;width:1.35em;height:1.35em;border-radius:50%;border:3px solid var(--c);font-weight:900;font-size:.72em;color:var(--chalk);background:#0d0d12;flex:none}
.pw-tower{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:.95rem}
.pw-tower,.pw-tower tr{border:none !important}
.pw-tower td,.pw-tower th{border:none !important;border-bottom:1px solid var(--line) !important}
.pw-tower td{padding:.28rem .4rem;white-space:nowrap}
.pw-tower tr.mine td{background:color-mix(in srgb,var(--team) 16%,transparent)}
.pw-tower tr.focus td{background:color-mix(in srgb,var(--team) 34%,transparent)}
.pw-tower .p{font-weight:900;width:1.8em;text-align:right;color:var(--tarmac)}
.pw-tower tr.focus .p,.pw-tower tr.mine .p{color:var(--chalk)}
.pw-tower .bar{width:4px;padding:0;background:var(--team)}
.pw-tower .code{font-weight:700;font-size:.9rem;letter-spacing:.3px}
.pw-tower .gap,.pw-tower .int{text-align:right;color:var(--chalk)}
.pw-tower .int{color:var(--tarmac)}
.pw-tower .pit{font-size:.7rem;font-weight:700;background:var(--chalk);color:#111;border-radius:2px;padding:0 .3em;margin-left:.3em}
.pw-tower .stops{color:var(--tarmac);text-align:center}
.pw-tower th{color:var(--tarmac);font-weight:400;font-size:.75rem;text-align:right;padding:.1rem .4rem}
.pw-banner{border-radius:4px;padding:.7rem 1rem;font-weight:900;font-style:italic;margin:.4rem 0;color:#111;background:var(--flag)}
.pw-sub{color:var(--tarmac);font-size:.85rem}
.pw-live{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:2px;background:var(--line);border-radius:4px;overflow:hidden;margin:.3rem 0 .8rem}
.pw-live>div{background:var(--asphalt);padding:.4rem .5rem}
.pw-bar{height:6px;border-radius:3px;background:rgba(128,128,128,0.25);overflow:hidden;margin-top:6px}
.pw-bar>span{display:block;height:100%}
.pw-tag{display:inline-block;padding:1px 8px;border-radius:3px;font-weight:700;font-size:.8rem}
.pw-plain{border-left:3px solid #4EA1FF;background:rgba(78,161,255,0.09);border-radius:0 4px 4px 0;padding:.5rem .8rem;margin:.3rem 0 .7rem;font-size:.93rem}
.pw-empty{background:var(--asphalt);border-radius:6px;padding:1.4rem 1.2rem;margin:.6rem 0;max-width:640px}
.pw-empty b{font-size:1.4rem;font-weight:900;font-style:italic;display:block;margin-bottom:.3rem}
[data-testid="stExpander"] details{border-color:var(--line) !important;border-radius:4px !important}
[data-baseweb="select"]>div{background:var(--asphalt) !important;border-color:var(--line) !important}
@media (max-width:1180px){
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3)){flex-wrap:wrap !important}
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3)) > [data-testid="stColumn"]{flex:1 1 360px !important;min-width:340px !important}
}
@media (max-width:640px){
  .block-container{padding:3.2rem .75rem 2rem !important}
  h1{font-size:1.55rem !important}
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{min-width:100% !important}
  .pw-strip>div{padding:.35rem .6rem}
  .pw-lap{font-size:1.25rem}
  .pw-flag{min-width:0}
  .pw-gp{flex-basis:100%}
  .pw-loss{margin-left:0;text-align:left;flex-basis:100%;border-top:1px solid var(--line)}
  .pw-pos{font-size:2.5rem}
  .pw-code{font-size:1.25rem}
  .pw-call{font-size:1.25rem;padding:.3rem 1rem .3rem .9rem}
  .pw-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .pw-live{grid-template-columns:repeat(3,minmax(0,1fr))}
  .pw-tower{font-size:.9rem}
  .pw-tower td{padding:.3rem .3rem}
}
</style>
"""


@st.cache_resource(show_spinner="Loading session for replay…", max_entries=4)
def get_replay(kind, key, year=None, gp=None, code="R"):
    if kind == "bundled":
        what, folder = BUNDLED[key]
        raw = load_fixture(folder)
        return RaceReplay(raw) if what == "race" else SessionReplay(raw)
    raw = load_openf1_race(int(year), gp, session=code)
    return RaceReplay(raw) if code in ("R", "S") else SessionReplay(raw)


def _record_forever():
    while True:
        try:
            record(LIVE_DIR, raw_log=False)
        except Exception:
            time.sleep(10)


@st.cache_resource
def ensure_recorder():
    t = threading.Thread(target=_record_forever, name="f1-live-recorder", daemon=True)
    t.start()
    return t


def sidebar():
    st.sidebar.header("Pit wall")
    qp = st.query_params
    mode = st.sidebar.radio("Mode", ["Live", "Replay"], index=0 if qp.get("mode", "live").lower() != "replay" else 1,
                            help="Live follows the session happening now. Replay steps through a past session.")
    loss = st.sidebar.number_input("Pit-stop time loss override (s)", min_value=0.0, max_value=40.0, value=0.0, step=0.5,
                                   help="0 = automatic: measured from this race's stops once 3+ have happened, otherwise a track default (est.).")
    refresh = st.sidebar.slider("Refresh every (s)", 2, 15, 3)
    gl.sidebar_toggle()
    return mode, (loss or None), refresh


def replay_controls():
    st.sidebar.divider()
    st.sidebar.subheader("Replay")
    choice = st.sidebar.radio("Session", list(BUNDLED) + ["Pick any session (OpenF1, 2023+)"], index=0)
    try:
        if choice in BUNDLED:
            rep = get_replay("bundled", choice)
        else:
            year = st.sidebar.number_input("Season", 2023, 2026, 2025)
            gp = st.sidebar.text_input("Grand Prix (name or city)", "Mexico")
            code = st.sidebar.selectbox("Session", ["R", "Q", "FP1", "FP2", "FP3", "S", "SQ"], format_func=lambda c: {"R": "Race", "Q": "Qualifying", "S": "Sprint", "SQ": "Sprint Qualifying"}.get(c, c))
            rep = get_replay("openf1", choice, year, gp, code)
    except Exception as exc:
        st.error(f"Could not load that session: {exc}")
        return None
    practice = isinstance(rep, SessionReplay)
    if st.session_state.get("pw_choice") != choice:
        st.session_state["pw_choice"] = choice
        st.session_state["pw_lap"] = 1
        st.session_state["pw_min"] = int(rep.duration_s // 60) + 1 if practice else 1
        st.session_state["pw_play"] = False
    st.session_state.setdefault("pw_play", False)
    st.session_state.setdefault("pw_lap", 1)
    st.session_state.setdefault("pw_min", int(rep.duration_s // 60) + 1 if practice else 1)
    c1, c2 = st.sidebar.columns(2)
    if c1.button("▶ Play" if not st.session_state.pw_play else "⏸ Pause", width="stretch"):
        st.session_state.pw_play = not st.session_state.pw_play
    if c2.button("⏮ Start", width="stretch"):
        st.session_state.pw_lap = 1
        st.session_state.pw_min = 1
    if practice:
        st.session_state.pw_min = min(max(int(st.session_state.pw_min), 1), int(rep.duration_s // 60) + 1)
    else:
        st.session_state.pw_lap = min(max(int(st.session_state.pw_lap), 1), rep.total_laps)
    return rep


def header(snap, result, feed_note):
    s = snap["session"]
    status = str(result.get("track_status") if result else s.get("track_status") or "1")
    label, colour = STATUS_STYLE.get(status, (f"STATUS {status}", "#888"))
    if result:
        progress = f"Lap {s.get('lap') or 0} <small>/ {result['total_laps']}</small>"
    elif s.get("remaining"):
        progress = f"{(s.get('remaining') or '')[:8]} <small>left</small>"
    else:
        progress = "Practice"
    live = "<span class='pw-live-dot'></span>" if feed_note.startswith("Live feed connected") else ""
    st.markdown(
        f"<div class='pw-strip'><div class='pw-flag' style='background:{colour}'>{label}</div>"
        f"<div class='pw-lap num'>{progress}</div>"
        f"<div class='pw-gp'>{s.get('meeting') or ''}<small>{s.get('name') or ''}</small></div>"
        + (f"<div class='pw-loss num'>Pit stop ≈{result['pit_loss']:.1f}s<small>{result['pit_loss_source']}</small></div>" if result else "")
        + "</div>"
        f"<div class='pw-feed'>{live}{feed_note}</div>",
        unsafe_allow_html=True,
    )
    return status


def sc_banner(result):
    if not result["neutralised"]:
        return
    lines = []
    for r in result["cars"]:
        plan = r["safety_car"]["SC" if result["neutralised"] == "SC" else "VSC"]
        verdict = "BOX NOW" if plan["box"] else "STAY OUT"
        lines.append(f"{r['car']['code']}: {verdict}")
    ds = next((r["double_stack"] for r in result["cars"] if r.get("double_stack")), None)
    extra = f" · {ds['advice']}" if ds and result["neutralised"] in ("SC", "VSC") else ""
    st.markdown(f"<div class='pw-banner'>{result['neutralised']} deployed. {' · '.join(lines)}{extra}</div>", unsafe_allow_html=True)


def fmt_gap(v, laps=0):
    if laps:
        return f"+{laps} lap{'s' if laps > 1 else ''}"
    return "—" if v is None else f"{v:+.1f}s"


def duel_text(d, ours):
    if d is None:
        return "—"
    if d.get("probability") is None:
        return d.get("note") or "—"
    p = d["probability"] * 100
    if ours:
        return f"Undercut on **{d['target']}** ({d['gap']:.1f}s ahead): **{p:.0f}%** chance it works (new {d['new_compound']}, fresh-tyre gain {d['fresh_delta']:.1f}s/lap)"
    return f"**{d['attacker']}** ({d['gap']:.1f}s behind) undercutting us: **{p:.0f}%** chance" + (" — cover by boxing on the lap they do." if p >= 40 else ".")


def driver_card(r, focus=False):
    car = r["car"]
    bg, fg = CALL_STYLE.get(r["call"], ("#374151", "#FFF"))
    with st.container(border=False):
        st.markdown(
            f"<div class='pw-hero' style='--team:{car['colour']}'><div class='pw-id'>"
            f"<div class='pw-pos'><small>P</small>{car['position']}</div>"
            f"<div><div class='pw-code'>{'⭐ ' if focus else ''}{car['code']}</div><div class='pw-name'>{car.get('name') or ''} · {car.get('team') or ''}</div></div></div>"
            f"<div class='pw-call' style='background:{bg};color:{fg}'><span>{r['call']}</span></div>"
            f"<div class='pw-why'>{r['why']}</div></div>",
            unsafe_allow_html=True,
        )
        gl.plain(gl.explain_call(r))
        behind = r.get("behind")
        ahead = r.get("ahead")
        cells = [
            ("Tyre", f"{tyre_dot(car.get('compound'))}{car.get('tyre_age')} laps"),
            ("Stops", str(car.get("stops"))),
            ("Ahead" + (f" ({ahead['code']})" if ahead else ""), fmt_gap(car.get("interval"), car.get("interval_laps"))),
            ("Behind" + (f" ({behind['code']})" if behind else ""), fmt_gap(behind.get("interval") if behind else None)),
        ]
        st.markdown("<div class='pw-grid'>" + "".join(f"<div><div class='pw-k'>{k}</div><div class='pw-v'>{v}</div></div>" for k, v in cells) + "</div>", unsafe_allow_html=True)
        bp = r["best_plan"]
        plan_txt = "No more stops" if bp and not bp["stops"] else (" → ".join(f"{c} lap {l}" for c, l in zip(bp["compounds"], bp["pit_laps"])) if bp else "—")
        rj = r["rejoin_now"]
        rj_txt = (f"P{rj['position']}" + (f", {rj['gap_ahead']:.1f}s behind {rj['car_ahead']} ({rj['car_ahead_tyres']})" if rj and rj["car_ahead"] else "") + (" ⚠ traffic" if rj and rj["traffic"] else "")) if rj else "—"
        cost = r["box_now_cost"]
        alt = r.get("alt_plan")
        alt_txt = ""
        if alt:
            alt_body = "no more stops" if not alt["stops"] else " → ".join(f"{c} lap {l}" for c, l in zip(alt["compounds"], alt["pit_laps"]))
            alt_txt = f" · **Plan B:** {alt_body} (+{alt['delta']:.1f}s)"
        st.markdown(
            f"**Plan A:** {plan_txt}{alt_txt}  \n"
            f"**Window:** {('laps ' + str(r['window'][0]) + '–' + str(r['window'][1])) if r['window'] else '—'} · "
            f"**Box now:** {('+' + format(cost, '.1f') + 's vs best' if cost is not None and cost > 0.05 else 'on the best plan') if cost is not None else '—'} → {r['box_now_compound'] or '—'}  \n"
            f"**Rejoin if box now:** {rj_txt}"
        )
        st.markdown("**Undercut threats**")
        st.markdown(f"🔺 {duel_text(r['attack'], True)}  \n🔻 {duel_text(r['defend'], False)}")
        sc, vsc = r["safety_car"]["SC"], r["safety_car"]["VSC"]
        def rj_short(x):
            return f"rejoin P{x['rejoin']['position']}" if x["rejoin"] else ""
        st.markdown(
            f"**If Safety Car now:** {'🟥 BOX' if sc['box'] else '🟩 STAY OUT'} — {sc['reason']} {rj_short(sc)}  \n"
            f"**If VSC now:** {'🟥 BOX' if vsc['box'] else '🟩 STAY OUT'} — stop costs ~{vsc['pit_loss']:.0f}s, {rj_short(vsc)}"
        )
        if r.get("double_stack"):
            st.caption(r["double_stack"]["advice"])
        w = r["wear"]
        slope = w["stint_slope"]
        slope_txt = "need 5 clean laps" if slope is None else ("improving (track rubbering in)" if slope < 0 else f"{slope:.3f} s/lap")
        st.markdown(
            f"**Tyre wear:** this stint {slope_txt} · field on {car.get('compound')}: {w['compound_slope']:.3f} s/lap ({w['compound_source']}) · "
            f"already ~{w['loss_vs_new']:.1f}s/lap slower than a new set (est.)"
        )
        if w["series"]:
            df = pd.DataFrame(w["series"])
            fig = go.Figure(go.Scatter(x=df["age"], y=df["time"], mode="markers+lines", line=dict(color=car["colour"])))
            st.plotly_chart(_font(charts.style(fig, None, "Tyre age (laps)", "Fuel-corrected lap (s)", 200)), key=f"wear_{car['number']}_{len(df)}")


def tower(snap, team, focus=None):
    rows = []
    for d in sorted([d for d in snap["drivers"] if d.get("position")], key=lambda d: d["position"]):
        mine = team.lower() in str(d.get("team") or "").lower()
        cls = "focus" if d["code"] == focus else ("mine" if mine else "")
        pit = "<span class='pit'>PIT</span>" if d.get("in_pit") else ("<span class='pit'>OUT</span>" if d.get("pit_out") else "")
        if d.get("retired"):
            gap, inter = "Out", ""
        elif d["position"] == 1:
            gap, inter = "Leader", ""
        else:
            gap, inter = fmt_gap(d.get("gap_to_leader"), d.get("laps_down")), fmt_gap(d.get("interval"), d.get("interval_laps"))
        rows.append(
            f"<tr class='{cls}' style='--team:{d.get('colour') or '#777'}'><td class='p'>{d['position']}</td><td class='bar'></td>"
            f"<td class='code'>{d['code']}{pit}</td><td class='gap'>{gap}</td><td class='int'>{inter}</td>"
            f"<td>{tyre_dot(d.get('compound'))}<span class='pw-sub'> {d.get('tyre_age') if d.get('tyre_age') is not None else ''}</span></td>"
            f"<td class='stops'>{d.get('stops') or 0}</td></tr>"
        )
    if not rows:
        st.info("No timing yet.")
        return
    head = "<tr><th></th><th></th><th style='text-align:left'>Driver</th><th>Gap</th><th>Int</th><th style='text-align:left'>Tyre</th><th style='text-align:center'>Pits</th></tr>"
    st.markdown(f"<table class='pw-tower'>{head}{''.join(rows)}</table>", unsafe_allow_html=True)
    gl.plain("Gap = seconds behind the leader. Int = seconds behind the car just ahead. The circle is the tyre (S soft, M medium, H hard, I inter, W wet) and the number is how many laps old it is. Pits = stops made.")


IST = "Asia/Kolkata"
RADIO_SHOWN = 6


def radio_panel(snap, team, focus, key):
    clips = snap.get("radio") or []
    st.subheader("Team radio")
    if not clips:
        st.caption("No radio clips yet this session.")
        return
    codes = set(team_codes(snap, team))
    only = st.toggle(f"{team} only", value=True, key=f"radio_only_{key}")
    shown = [c for c in clips if (c["code"] in codes) or not only]
    if not shown:
        st.caption(f"No {team} radio yet. Turn off the filter to hear everyone.")
        return
    for c in shown[:RADIO_SHOWN]:
        try:
            when = pd.Timestamp(c["utc"]).tz_localize("UTC") if pd.Timestamp(c["utc"]).tzinfo is None else pd.Timestamp(c["utc"])
            label = when.tz_convert(IST).strftime("%H:%M:%S IST")
        except Exception:
            label = ""
        star = "⭐ " if c["code"] == focus else ""
        st.markdown(f"**{star}{c['code']}** <span class='pw-sub'>{label}</span>", unsafe_allow_html=True)
        st.audio(c["url"], format="audio/mpeg")
    st.caption("Clips are the ones F1 makes public, a few seconds to a minute after they air. Newest first.")


@st.cache_data(ttl=86400, show_spinner=False)
def circuit_outline(circuit_key, year):
    import requests

    for y in (year, (year or 0) - 1, (year or 0) - 2):
        if not circuit_key or not y:
            break
        try:
            r = requests.get(f"https://api.multiviewer.app/api/v1/circuits/{int(circuit_key)}/{int(y)}", headers={"User-Agent": "f1-pitwall"}, timeout=10)
            if r.ok:
                d = r.json()
                if d.get("x") and d.get("y"):
                    corners = [(c["number"], c["trackPosition"]["x"], c["trackPosition"]["y"]) for c in d.get("corners") or [] if c.get("trackPosition")]
                    return {"x": d["x"], "y": d["y"], "rotation": float(d.get("rotation") or 0), "corners": corners}
        except Exception:
            continue
    return None


def _rotate(xs, ys, deg):
    import math

    a = math.radians(deg)
    c, s_ = math.cos(a), math.sin(a)
    return [x * c - y * s_ for x, y in zip(xs, ys)], [x * s_ + y * c for x, y in zip(xs, ys)]


def _outline_for(snap):
    from f1analytics.pitwall.tracks import circuit_key_for

    s = snap.get("session") or {}
    key = snap.get("circuit_key") or circuit_key_for(s.get("circuit"), s.get("meeting"))
    try:
        return circuit_outline(key, int(s.get("year") or 0) or None) if key else None
    except Exception:
        return None


def _draw_outline(fig, outline):
    ox, oy = _rotate(outline["x"], outline["y"], outline["rotation"])
    fig.add_trace(go.Scatter(x=ox + ox[:1], y=oy + oy[:1], mode="lines", line=dict(color="#3A3A48", width=9), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=ox + ox[:1], y=oy + oy[:1], mode="lines", line=dict(color="#22222C", width=5), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=[ox[0]], y=[oy[0]], mode="markers", marker=dict(symbol="line-ns", size=16, line=dict(width=3, color="#F3F3F5")), hoverinfo="skip"))
    if outline.get("corners"):
        nums, cx, cy = zip(*outline["corners"])
        rx, ry = _rotate(list(cx), list(cy), outline["rotation"])
        fig.add_trace(go.Scatter(x=rx, y=ry, mode="text", text=[str(n) for n in nums], textfont=dict(size=9, color="#6B6B7A"), hoverinfo="skip"))
    return ox, oy


def _track_figure(fig, height=300):
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    fig.update_layout(showlegend=False, height=height, margin=dict(l=4, r=4, t=4, b=4))
    return _font(fig)


def real_track_map(snap, team, focus):
    pos = snap.get("positions") or {}
    if not pos:
        return False
    by_num = {d["number"]: d for d in snap.get("drivers", [])}
    outline = _outline_for(snap)
    rot = outline["rotation"] if outline else 0.0
    fig = go.Figure()
    if outline:
        _draw_outline(fig, outline)
    xs, ys, cols, sizes, labels, hovers = [], [], [], [], [], []
    for num, p in pos.items():
        d = by_num.get(num)
        if d is None or d.get("retired"):
            continue
        (x,), (y,) = _rotate([p["x"]], [p["y"]], rot)
        xs.append(x); ys.append(y)
        mine = team.lower() in str(d.get("team") or "").lower()
        cols.append(d.get("colour") or "#888")
        sizes.append(18 if d["code"] == focus else (13 if mine else 9))
        labels.append(d["code"] if (mine or (d.get("position") or 99) <= 5) else "")
        hovers.append(f"P{d.get('position')} {d['code']}")
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers+text", text=labels, textposition="top center",
                             marker=dict(size=sizes, color=cols, line=dict(width=1, color="#222")), hovertext=hovers, hoverinfo="text"))
    _track_figure(fig)
    st.subheader("Track map (live GPS)")
    st.plotly_chart(fig, key=f"gps_{snap.get('positions_utc')}", config={"displayModeBar": False, "staticPlot": False})
    st.caption("Real car positions from F1TV. Circuit outline: MultiViewer.")
    return True


def track_map(snap, team, focus):
    if real_track_map(snap, team, focus):
        return
    cars = [d for d in snap.get("drivers", []) if not d.get("retired") and d.get("position") and d.get("gap_to_leader") is not None]
    if len(cars) < 2:
        return
    ref = [d["last_lap"] for d in cars if d.get("last_lap")]
    lap = float(pd.Series(ref).median()) if ref else 90.0
    outline = _outline_for(snap)
    if outline:
        fig = go.Figure()
        ox, oy = _draw_outline(fig, outline)
        n = len(ox)
        xs, ys, cols, sizes, labels, hovers = [], [], [], [], [], []
        for d in sorted(cars, key=lambda d: d["position"], reverse=True):
            frac = (d["gap_to_leader"] % lap) / lap
            i = int(round((1 - frac) % 1 * n)) % n
            mine = team.lower() in str(d.get("team") or "").lower()
            xs.append(ox[i]); ys.append(oy[i])
            cols.append(d.get("colour") or "#888")
            sizes.append(17 if d["code"] == focus else (13 if mine else 9))
            labels.append(d["code"] if (mine or d["position"] <= 3) else "")
            hovers.append(f"P{d['position']} {d['code']} " + ("leader" if d["position"] == 1 else f"+{d['gap_to_leader']:.1f}s"))
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers+text", text=labels, textposition="top center", textfont=dict(size=11, color="#F3F3F5"),
                                 marker=dict(size=sizes, color=cols, line=dict(width=1.5, color="#15151E")), hovertext=hovers, hoverinfo="text"))
        st.subheader("Track (from gaps)")
        st.plotly_chart(_track_figure(fig, 320), key=f"trackmap_{snap['session'].get('lap')}_{len(xs)}", config={"displayModeBar": False})
        st.caption("The leader is drawn at the start line and everyone else behind by their time gap. An estimate: exact GPS positions need F1TV sign-in.")
        return
    rows = []
    for d in cars:
        frac = (d["gap_to_leader"] % lap) / lap
        mine = team.lower() in str(d.get("team") or "").lower()
        rows.append({"code": d["code"], "theta": -frac * 360, "colour": d["colour"], "size": 18 if d["code"] == focus else (14 if mine else 10),
                     "text": f"P{d['position']} {d['code']} {('+' + format(d['gap_to_leader'], '.1f') + 's') if d['position'] > 1 else 'leader'}"})
    df = pd.DataFrame(rows)
    fig = go.Figure(go.Scatterpolar(r=[1] * 361, theta=list(range(361)), mode="lines", line=dict(color="#2E2E3A", width=10), hoverinfo="skip"))
    fig.add_trace(go.Scatterpolar(
        r=[1] * len(df), theta=df["theta"], mode="markers+text", text=df["code"], textposition="top center",
        marker=dict(size=df["size"], color=df["colour"], line=dict(width=1.5, color="#15151E")), hovertext=df["text"], hoverinfo="text",
    ))
    fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(visible=False, range=[0, 1.25]), angularaxis=dict(visible=False, rotation=90, direction="clockwise")),
                      showlegend=False, height=320, margin=dict(l=10, r=10, t=10, b=10))
    st.subheader("Track (from gaps)")
    st.plotly_chart(_font(fig), key=f"track_{snap['session'].get('lap')}_{len(df)}", config={"displayModeBar": False})
    st.caption(f"Leader at the top, everyone else placed by their time gap on a {lap:.0f}s lap. An estimate, not GPS: real car positions are paid F1TV data.")


def race_control(snap):
    msgs = list(reversed(snap.get("race_control") or []))[:8]
    for m in msgs:
        note = gl.flag_note(m.get("message")) if gl.beginner_on() else ""
        note = f"<div class='pw-sub' style='margin:2px 0 6px 0'>{note}</div>" if note else ""
        st.markdown(f"<span class='pw-sub'>Lap {m.get('lap') or '–'}</span> {m.get('message')}{note}", unsafe_allow_html=True)


def team_codes(snap, team):
    return [d["code"] for d in sorted(snap.get("drivers", []), key=lambda d: d.get("position") or 99) if team.lower() in str(d.get("team") or "").lower()]


def _set_param(name, value):
    if value and st.query_params.get(name) != value:
        st.query_params[name] = value


def _team_changed():
    st.session_state.pop("pw_driver", None)


def follow_picker(snap):
    drivers = [d for d in snap.get("drivers", []) if d.get("code")]
    if not drivers:
        return None, None
    order = sorted(drivers, key=lambda d: d.get("position") or 99)
    teams = list(dict.fromkeys(d.get("team") or "?" for d in order))
    qp = st.query_params
    want_driver = str(qp.get("driver", "")).upper()
    want_team = str(qp.get("team", "")).lower()
    by_code = {d["code"]: d for d in drivers}
    if st.session_state.get("pw_team") not in teams:
        if want_driver in by_code:
            default_team = by_code[want_driver].get("team")
        else:
            default_team = next((t for t in teams if want_team and (want_team in t.lower() or t.lower() in want_team)), None)
            default_team = default_team or (by_code["HAM"].get("team") if "HAM" in by_code else teams[0])
        st.session_state["pw_team"] = default_team
    c1, c2 = st.columns(2)
    team = c1.selectbox("Your team", teams, key="pw_team", on_change=_team_changed)
    mates = [d for d in order if d.get("team") == team]
    codes = [d["code"] for d in mates]
    if st.session_state.get("pw_driver") not in codes:
        st.session_state["pw_driver"] = want_driver if want_driver in codes else ("HAM" if "HAM" in codes else codes[0])
    names = {d["code"]: f"{d['code']} · {d.get('name') or ''}".strip(" ·") for d in mates}
    focus = c2.selectbox("Your driver", codes, key="pw_driver", format_func=names.get)
    _set_param("team", team)
    _set_param("driver", focus)
    colour = by_code[focus].get("colour") or "#888"
    st.markdown(f"<div class='pw-sub' style='border-left:4px solid {colour};padding-left:8px;margin:-4px 0 8px'>Following ⭐ {focus} · share this link and it opens on them.</div>", unsafe_allow_html=True)
    return team, focus


def live_car(snap, focus):
    year = int((snap.get("session") or {}).get("year") or 2026)
    num = next((d["number"] for d in snap.get("drivers", []) if d["code"] == focus), None)
    car = (snap.get("car") or {}).get(num) if num else None
    if not car:
        return
    if year >= 2026:
        aero_k, drs = "Wings", ("STRAIGHT" if car["drs_open"] else "CORNER")
    else:
        aero_k, drs = "DRS", ("OPEN" if car["drs_open"] else ("ready" if car["drs"] == 8 else "closed"))
    drs_bg = "var(--live, #1E9E5A)" if car["drs_open"] else "rgba(128,128,128,0.35)"
    st.markdown(
        f"**{focus} right now (F1TV car data)**"
        f"<div class='pw-live'>"
        f"<div><div class='pw-k'>Speed</div><div class='pw-v'>{car['speed']} km/h</div></div>"
        f"<div><div class='pw-k'>Gear</div><div class='pw-v'>{car['gear']}</div></div>"
        f"<div><div class='pw-k'>{aero_k}</div><div class='pw-v'><span class='pw-tag' style='background:{drs_bg}'>{drs}</span></div></div>"
        f"<div><div class='pw-k'>Throttle {car['throttle']}%</div><div class='pw-bar'><span style='width:{max(0, min(100, car['throttle']))}%;background:#1E9E5A'></span></div></div>"
        f"<div><div class='pw-k'>Brake</div><div class='pw-bar'><span style='width:{100 if car['brake'] else 0}%;background:#E10600'></span></div></div>"
        f"<div><div class='pw-k'>RPM</div><div class='pw-v'>{car['rpm']:,}</div></div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if year >= 2026:
        st.caption("Wings reading (Straight vs Corner mode) comes from the old DRS channel in F1's feed. Not yet confirmed on 2026 cars; first real check is FP1.")


def car_panel(snap, focus, teammate):
    live_car(snap, focus)
    sp = speed_profile(snap, focus, teammate)
    st.markdown(f"**{focus}'s car (estimated from speed traps)**")
    if not sp:
        st.caption("Needs about 10 timed laps with speed-trap readings.")
        return
    mate = f" · vs {sp['teammate']['code']}: {sp['teammate']['delta']:+.1f} km/h" if sp.get("teammate") else ""
    st.markdown(
        f"Top speed **{sp['top_speed']:.0f} km/h**, {sp['delta']:+.1f} km/h vs field (#{sp['rank']} of {sp['cars']}){mate}  \n"
        f"**Wing level (est.):** {sp['level']}. Real wing angles and engine modes are private to the teams; this reads them from straight-line speed."
    )
    hints = mode_hints(snap, focus)
    if hints:
        st.markdown("**Mode hints, recent laps (est.)**")
        for h in hints[-5:]:
            st.markdown(f"<span class='pw-sub'>Lap {h['lap']}</span> {h['speed_trap']:.0f} km/h ({h['vs_normal']:+.0f}) · {h['note']}", unsafe_allow_html=True)
    gl.words("car", "Car words explained")


def render(snap, loss, feed_note):
    top_l, top_r = st.columns([3, 2], vertical_alignment="bottom", gap="medium")
    with top_r:
        team, focus = follow_picker(snap)
    if team is None:
        st.info("Waiting for the driver list from the session…")
        return
    kind = str((snap.get("session") or {}).get("type") or "").lower()
    if kind and kind not in RACE_TYPES:
        with top_l:
            header(snap, None, feed_note)
        render_practice(snap, team, focus, feed_note)
        return
    result = analyse(snap, team=team, pit_loss=loss)
    with top_l:
        status = header(snap, result, feed_note)
    sc_banner(result)
    if not result["cars"]:
        st.warning(f"No running {team} cars in this session.")
    ordered = sorted(result["cars"], key=lambda r: r["car"]["code"] != focus)
    left, mid, right = st.columns([5, 4, 3], gap="medium")
    with left:
        for i, r in enumerate(ordered):
            if i == 0:
                driver_card(r, focus=True)
                if status != "1":
                    gl.plain(gl.status_text(status))
                gl.plain(f"A pit stop here costs about {result['pit_loss']:.0f} seconds compared with staying out. Every call weighs new, faster tyres against that cost.")
                gl.words("call", "Strategy words explained")
                teammate = ordered[1]["car"]["code"] if len(ordered) > 1 else None
                car_panel(snap, r["car"]["code"], teammate)
                st.divider()
            else:
                with st.expander(f"Teammate: P{r['car']['position']} {r['car']['code']} · {r['call']}", expanded=False):
                    driver_card(r)
    with mid:
        st.subheader("Timing")
        tower(snap, team, focus)
        gl.words("timing", "Timing words explained")
    with right:
        track_map(snap, team, focus)
        radio_panel(snap, team, focus, "race")
        st.subheader("Race control")
        race_control(snap)
    from f1analytics.ui.styles_panel import start_tyres_section, styles_section

    if (snap.get("session") or {}).get("lap") in (None, 0, 1):
        start_tyres_section(snap)
    styles_section(snap, focus)
    gl.flags_panel("race")
    gl.glossary("race")
    with st.expander("How the calls are made"):
        st.markdown(
            f"- **Tyre model:** lap time = α + β·tyre age per compound, fitted live on clean laps (no pit, Safety Car or lap 1) after fuel correction "
            f"(0.033 s/kg × 105 kg start fuel, est.). Until a compound has ~60 clean laps it is blended with defaults "
            f"(soft 0.09, medium 0.06, hard 0.04 s/lap, est.).\n"
            f"- **Box call:** every 0-, 1- and 2-stop plan for the rest of the race is timed (stint cost L·α + β·(L·age + L(L−1)/2) + {result['pit_loss']:.1f}s per stop, "
            f"two dry compounds required). 'Box this lap' means stopping now is within {1.0:.0f}s of the best plan.\n"
            f"- **Rejoin:** your gap to the leader + pit loss, placed among everyone else's current gaps; under 1.0s to the car ahead = traffic.\n"
            f"- **Undercut %:** 3,000 simulated stops with random pit-stop times, Safety Cars, traffic and lap noise (see Strategy Simulator tab).\n"
            f"- **Safety Car:** a stop costs about 45% (SC) or 65% (VSC) of a green-flag stop (est.). Box if a stop is still needed."
        )


def render_practice(snap, team, focus, feed_note):
    summary = practice_summary(snap, team, focus or "")
    gl.plain("This is practice, not a race. Teams test car setups and tyres, so the order here does not count. Watch the long runs: they are the best clue to Sunday's race pace.")
    left, mid, right = st.columns([5, 4, 3], gap="medium")
    with left:
        for c in summary["cars"]:
            d = c["car"]
            is_focus = d["code"] == focus
            best = f"{int(d['best_lap'] // 60)}:{d['best_lap'] % 60:06.3f}" if d.get("best_lap") else "no time yet"
            gap = f"+{c['gap_to_fastest']:.3f}s" if c["gap_to_fastest"] else ("fastest" if d.get("best_lap") else "—")
            status = "In the garage / pit lane" if d.get("in_pit") else ("Out-lap" if d.get("pit_out") else "On track")
            body = (
                f"<div class='pw-hero' style='--team:{d['colour']}'><div class='pw-id'>"
                f"<div class='pw-pos'><small>P</small>{d['position']}</div>"
                f"<div><div class='pw-code'>{'⭐ ' if is_focus else ''}{d['code']}</div><div class='pw-name'>{d.get('name') or ''} · {d.get('team') or ''}</div></div></div>"
                f"<div class='pw-why'>{status}</div></div>"
                f"<div class='pw-grid'>"
                f"<div><div class='pw-k'>Best lap</div><div class='pw-v'>{best}</div></div>"
                f"<div><div class='pw-k'>Gap to P1</div><div class='pw-v'>{gap}</div></div>"
                f"<div><div class='pw-k'>Laps run</div><div class='pw-v'>{d.get('laps')}</div></div>"
                f"<div><div class='pw-k'>Tyre</div><div class='pw-v'>{tyre_dot(d.get('compound'))}{d.get('tyre_age')} laps</div></div>"
                f"</div>"
            )
            if is_focus:
                st.markdown(body, unsafe_allow_html=True)
                if c["runs"]:
                    st.markdown("**Long runs (race-pace practice)**")
                    for r in c["runs"]:
                        vs = f", {r['vs_best']:+.2f}s vs best ({r['best_driver']})" if r["vs_best"] is not None else ""
                        wear = f", wear ~{r['wear']:.3f} s/lap" if r["wear"] is not None else ""
                        st.markdown(f"{r['compound']}: {r['laps']} laps avg **{r['avg']:.3f}s** (#{r['rank']} of {r['of']} on this tyre{vs}{wear})")
                else:
                    st.caption("No long run yet (needs 5+ consistent laps on one set).")
                teammate = next((x["car"]["code"] for x in summary["cars"] if x["car"]["code"] != focus), None)
                car_panel(snap, focus, teammate)
                st.divider()
            else:
                with st.expander(f"Teammate: P{d['position']} {d['code']} · {best} ({gap})"):
                    st.markdown(body, unsafe_allow_html=True)
        if not summary["cars"]:
            st.info(f"No {team} times yet.")
    with mid:
        st.subheader("Timing (best laps)")
        tower(snap, team, focus)
        gl.words("timing", "Timing words explained")
    with right:
        if len(summary["wear"]):
            st.subheader("Tyre wear from long runs (for Sunday)")
            st.dataframe(summary["wear"].rename(columns={"compound": "Tyre", "runs": "Runs", "wear_s_per_lap": "Wear s/lap", "avg_pace": "Avg lap s"}).round(3), hide_index=True)
            st.caption("Practice fuel loads are unknown, so wear here is a rough guide (burning fuel hides some wear).")
        radio_panel(snap, team, focus, "practice")
        st.subheader("Race control")
        race_control(snap)
        gl.words("practice", "Practice words explained")
    from f1analytics.ui.styles_panel import start_tyres_section, styles_section

    start_tyres_section(snap)
    styles_section(snap, focus)
    gl.flags_panel("practice")
    gl.glossary("practice")


MAX_TRIES = 5


def _owner_key():
    import os

    return os.environ.get("PITWALL_KEY", "")


def owner_view():
    import os

    if not _owner_key():
        return not (os.environ.get("F1_USERNAME") and os.environ.get("F1_PASSWORD"))
    return bool(st.session_state.get("pw_owner"))


def owner_signin():
    import hmac

    key = _owner_key()
    if not key:
        return
    if st.session_state.get("pw_owner"):
        c1, c2 = st.columns([3, 1])
        c1.caption("🔓 Signed in as owner: F1TV car positions and car data are on.")
        if c2.button("Sign out", key="pw_signout"):
            st.session_state["pw_owner"] = False
            st.rerun()
        return
    with st.expander("🔒 Owner sign-in (F1TV data)"):
        tries = st.session_state.get("pw_tries", 0)
        if tries >= MAX_TRIES:
            st.error("Too many wrong tries. Reload the page to try again.")
            return
        with st.form("pw_signin", clear_on_submit=True, border=False):
            given = st.text_input("Owner passphrase", type="password", key="pw_pass", help="The PITWALL_KEY you saved in the app's Secrets.")
            ok = st.form_submit_button("Sign in", type="primary")
        if ok:
            if given and hmac.compare_digest(given.encode(), key.encode()):
                st.session_state["pw_owner"] = True
                st.session_state["pw_tries"] = 0
                st.rerun()
            else:
                st.session_state["pw_tries"] = tries + 1
                st.error("That passphrase doesn't match. Check the PITWALL_KEY in your app's Secrets.")
        st.caption("Everyone else sees the free timing data. Your F1TV login stays in the app's Secrets and is never shown on the page.")


def strip_f1tv(snap):
    if snap and not owner_view():
        snap = dict(snap, positions={}, car={})
    return snap


def f1tv_badge(snap):
    feed = (snap or {}).get("feed") or {}
    if (snap or {}).get("positions"):
        return "F1TV ✓ GPS + car data"
    if feed.get("f1tv"):
        return "F1TV signed in"
    return "free data"


def main(autorecord=False):
    st.set_page_config(page_title="F1 Pit Wall", page_icon="🏁", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
    from f1analytics.live.auth import load_streamlit_secrets

    load_streamlit_secrets()
    if autorecord:
        ensure_recorder()
    mode, loss, refresh = sidebar()
    st.title("F1 Pit Wall")
    rep = replay_controls() if mode == "Replay" else None
    run(mode, loss, refresh, rep)
    owner_signin()


def run(mode, loss, refresh, rep):


    @st.fragment(run_every=refresh)
    def live_view():
        snap, age = read_current()
        if snap is None:
            st.markdown(
                "<div class='pw-empty'><b>Waiting for the live feed</b>"
                "The app connects to F1 live timing by itself and fills in within a minute once a session is running. "
                "Between sessions you can step through a past race lap by lap.</div>",
                unsafe_allow_html=True,
            )
            feed, ago = read_feed()
            if feed is None:
                st.caption("Starting the connection to F1 live timing…")
            elif feed.get("connected"):
                st.caption(f"Connected to F1 live timing {ago:.0f}s ago, waiting for the first data.")
            else:
                st.caption(f"Can't reach F1 live timing yet, retrying: {feed.get('error') or 'no reply'}")
            if st.button("Watch the 2026 US GP replay", type="primary"):
                st.query_params["mode"] = "replay"
                st.rerun(scope="app")
            return
        snap = strip_f1tv(snap)
        feed = snap.get("feed") or {}
        status = (snap.get("session") or {}).get("status")
        note = f"Live feed {'connected' if feed.get('connected') else 'reconnecting…'} · {f1tv_badge(snap)} · updated {age:.0f}s ago · session {status or '?'}"
        if age > 30 and status not in ("Finished", "Finalised", "Ends", "Inactive"):
            st.warning(f"No update for {age:.0f}s: the feed is reconnecting or no session is running.")
        render(snap, loss, note)

    @st.fragment(run_every=refresh)
    def replay_view():
        if rep is None:
            return
        if isinstance(rep, SessionReplay):
            total = int(rep.duration_s // 60) + 1
            if st.session_state.pw_play and st.session_state.pw_min < total:
                st.session_state.pw_min = min(total, st.session_state.pw_min + 2)
            minute = st.slider("Minute of session", 1, total, key="pw_min")
            snap = rep.snapshot_at(minute * 60)
        else:
            if st.session_state.pw_play and st.session_state.pw_lap < rep.total_laps:
                st.session_state.pw_lap += 1
            lap = st.slider("Lap", 1, rep.total_laps, key="pw_lap")
            snap = rep.snapshot(lap)
        render(snap, loss, f"Replay · {'playing' if st.session_state.pw_play else 'paused'}")

    if mode == "Live":
        live_view()
    else:
        replay_view()
