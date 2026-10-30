import warnings
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import threading
import time

from f1analytics.live.recorder import LIVE_DIR, read_current, record
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
TEAMS = ["Ferrari", "McLaren", "Mercedes", "Red Bull", "Aston Martin", "Williams", "Alpine", "Haas", "Racing Bulls", "Audi", "Cadillac"]
CALL_STYLE = {
    "BOX THIS LAP": ("#E10600", "#FFFFFF"),
    "BOX NEXT LAP": ("#F5A623", "#111111"),
    "STAY OUT": ("#1E9E5A", "#FFFFFF"),
    "IN PIT": ("#6B7280", "#FFFFFF"),
}
STATUS_STYLE = {
    "1": ("GREEN FLAG", "#1E9E5A"),
    "2": ("YELLOW", "#F5C518"),
    "4": ("SAFETY CAR", "#F5C518"),
    "5": ("RED FLAG", "#E10600"),
    "6": ("VIRTUAL SAFETY CAR", "#F5C518"),
    "7": ("VSC ENDING", "#F5C518"),
}

CSS = """
<style>
.pw-pill{display:inline-block;padding:4px 12px;border-radius:999px;font-weight:700;font-size:0.9rem;margin-right:8px}
.pw-call{border-radius:10px;padding:14px 16px;font-size:1.6rem;font-weight:800;letter-spacing:0.5px;margin:6px 0 4px}
.pw-why{opacity:0.9;font-size:0.95rem;margin-bottom:8px}
.pw-card{border:1px solid rgba(128,128,128,0.35);border-top:6px solid var(--team);border-radius:12px;padding:12px 14px;margin-bottom:12px}
.pw-head{font-size:1.4rem;font-weight:800}
.pw-sub{opacity:0.75;font-size:0.85rem}
.pw-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 16px;margin:4px 0 10px}
.pw-k{opacity:0.7;font-size:0.8rem}
.pw-v{font-size:1.15rem;font-weight:700;white-space:nowrap}
.pw-focus{border:2px solid var(--team);border-radius:14px;padding:4px 10px 10px;margin-bottom:14px}
.pw-banner{border-radius:10px;padding:12px 16px;font-weight:700;margin:8px 0;color:#111}
.pw-live{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px 12px;margin:6px 0 10px}
.pw-bar{height:6px;border-radius:3px;background:rgba(128,128,128,0.25);overflow:hidden;margin-top:4px}
.pw-bar>span{display:block;height:100%}
.pw-plain{border-left:4px solid #3B82F6;background:rgba(59,130,246,0.12);border-radius:6px;padding:8px 12px;margin:4px 0 10px;font-size:0.95rem}
.pw-tag{display:inline-block;padding:2px 8px;border-radius:6px;font-weight:700;font-size:0.8rem}
[data-testid="stToolbar"]{display:none}
@media (max-width: 640px){
  .block-container{padding-top:1.2rem !important;padding-left:0.8rem !important;padding-right:0.8rem !important}
  h1{font-size:1.7rem !important}
  .pw-call{font-size:1.3rem;padding:10px 12px}
  .pw-head{font-size:1.15rem}
  .pw-v{font-size:1rem}
  .pw-pill{font-size:0.75rem;padding:3px 9px;margin-bottom:4px}
  .pw-card{padding:10px 12px}
  .pw-live{grid-template-columns:repeat(3,minmax(0,1fr))}
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
    team_q = qp.get("team", "Ferrari")
    team = st.sidebar.selectbox("Team", TEAMS, index=TEAMS.index(team_q) if team_q in TEAMS else 0)
    loss = st.sidebar.number_input("Pit-stop time loss override (s)", min_value=0.0, max_value=40.0, value=0.0, step=0.5,
                                   help="0 = automatic: measured from this race's stops once 3+ have happened, otherwise a track default (est.).")
    refresh = st.sidebar.slider("Refresh every (s)", 2, 15, 3)
    gl.sidebar_toggle()
    return mode, team, (loss or None), refresh


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
    progress = f"LAP {s.get('lap') or 0} / {result['total_laps']}" if result else (f"{(s.get('remaining') or '')[:8]} LEFT" if s.get("remaining") else "PRACTICE")
    st.markdown(
        f"<span class='pw-pill' style='background:{colour};color:#111'>{label}</span>"
        f"<span class='pw-pill' style='background:#1F2937;color:#fff'>{progress}</span>"
        f"<span class='pw-pill' style='background:#1F2937;color:#fff'>{s.get('meeting') or ''} · {s.get('name') or ''}</span>"
        f"<span class='pw-sub'>{feed_note}</span>",
        unsafe_allow_html=True,
    )
    gl.plain(gl.status_text(status) if result or status != "1" else "")
    if result:
        st.caption(f"Pit-stop loss used: **{result['pit_loss']:.1f} s** ({result['pit_loss_source']}).")
        gl.plain(f"A pit stop here costs about {result['pit_loss']:.0f} seconds compared with staying out. Every call below weighs new, faster tyres against that cost.")


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
    st.markdown(f"<div class='pw-banner' style='background:#F5C518'>⚠ {result['neutralised']} DEPLOYED — {' · '.join(lines)}{extra}</div>", unsafe_allow_html=True)


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
            f"<div class='pw-card' style='--team:{car['colour']}'><div class='pw-head'>{'⭐ ' if focus else ''}P{car['position']} · {car['code']} "
            f"<span class='pw-sub'>{car.get('name') or ''}</span></div>"
            f"<div class='pw-call' style='background:{bg};color:{fg}'>{r['call']}</div>"
            f"<div class='pw-why'>{r['why']}</div></div>",
            unsafe_allow_html=True,
        )
        gl.plain(gl.explain_call(r))
        behind = r.get("behind")
        ahead = r.get("ahead")
        cells = [
            ("Tyre", f"{car.get('compound') or '?'} · {car.get('tyre_age')} laps"),
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
            st.plotly_chart(charts.style(fig, None, "Tyre age (laps)", "Fuel-corrected lap (s)", 200), key=f"wear_{car['number']}_{len(df)}")


def tower(snap, team):
    rows, mine = [], []
    for d in sorted([d for d in snap["drivers"] if d.get("position")], key=lambda d: d["position"]):
        pit = " IN" if d.get("in_pit") else (" OUT" if d.get("pit_out") else "")
        rows.append({
            "P": d["position"], "Car": d["code"] + pit,
            "Gap": "OUT" if d.get("retired") else ("Leader" if d["position"] == 1 else fmt_gap(d.get("gap_to_leader"), d.get("laps_down"))),
            "Int": fmt_gap(d.get("interval"), d.get("interval_laps")) if d["position"] > 1 and not d.get("retired") else "",
            "Tyre": f"{(d.get('compound') or '?')[:1]}{d.get('tyre_age')}",
            "Pits": d.get("stops"),
        })
        mine.append(team.lower() in str(d.get("team") or "").lower())
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("No timing yet.")
        return
    st.dataframe(df.style.apply(lambda r: ["background-color: rgba(225,6,0,0.25)" if mine[r.name] else "" for _ in r], axis=1),
                 hide_index=True, height=min(36 * (len(df) + 1), 820))
    gl.plain("Gap = seconds behind the leader. Int = seconds behind the car just ahead. Tyre M12 = Medium tyres, 12 laps old (S soft, H hard, I inter, W wet). Pits = stops made. Red rows = your team.")


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
                    return {"x": d["x"], "y": d["y"], "rotation": float(d.get("rotation") or 0)}
        except Exception:
            continue
    return None


def _rotate(xs, ys, deg):
    import math

    a = math.radians(deg)
    c, s_ = math.cos(a), math.sin(a)
    return [x * c - y * s_ for x, y in zip(xs, ys)], [x * s_ + y * c for x, y in zip(xs, ys)]


def real_track_map(snap, team, focus):
    pos = snap.get("positions") or {}
    if not pos:
        return False
    by_num = {d["number"]: d for d in snap.get("drivers", [])}
    year = (snap.get("session") or {}).get("year")
    outline = circuit_outline(snap.get("circuit_key"), year)
    rot = outline["rotation"] if outline else 0.0
    fig = go.Figure()
    if outline:
        ox, oy = _rotate(outline["x"], outline["y"], rot)
        fig.add_trace(go.Scatter(x=ox + ox[:1], y=oy + oy[:1], mode="lines", line=dict(color="rgba(150,150,150,0.55)", width=6), hoverinfo="skip"))
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
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    fig.update_layout(showlegend=False, height=300, margin=dict(l=4, r=4, t=4, b=4))
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
    rows = []
    for d in cars:
        frac = (d["gap_to_leader"] % lap) / lap
        mine = team.lower() in str(d.get("team") or "").lower()
        rows.append({"code": d["code"], "theta": -frac * 360, "colour": d["colour"], "size": 18 if d["code"] == focus else (14 if mine else 10),
                     "text": f"P{d['position']} {d['code']} {('+' + format(d['gap_to_leader'], '.1f') + 's') if d['position'] > 1 else 'leader'}"})
    df = pd.DataFrame(rows)
    fig = go.Figure(go.Scatterpolar(
        r=[1] * len(df), theta=df["theta"], mode="markers+text", text=df["code"], textposition="top center",
        marker=dict(size=df["size"], color=df["colour"], line=dict(width=1, color="#888")), hovertext=df["text"], hoverinfo="text",
    ))
    fig.update_layout(polar=dict(radialaxis=dict(visible=False, range=[0, 1.25]), angularaxis=dict(visible=False, rotation=90, direction="clockwise")),
                      showlegend=False, height=320, margin=dict(l=10, r=10, t=10, b=10))
    st.subheader("Track (from gaps)")
    st.plotly_chart(fig, key=f"track_{snap['session'].get('lap')}_{len(df)}", config={"displayModeBar": False})
    st.caption(f"Leader at the top, everyone else placed by their time gap on a {lap:.0f}s lap. An estimate, not GPS: real car positions are paid F1TV data.")


def race_control(snap):
    msgs = list(reversed(snap.get("race_control") or []))[:8]
    for m in msgs:
        note = gl.flag_note(m.get("message")) if gl.beginner_on() else ""
        note = f"<div class='pw-sub' style='margin:2px 0 6px 0'>{note}</div>" if note else ""
        st.markdown(f"<span class='pw-sub'>Lap {m.get('lap') or '–'}</span> {m.get('message')}{note}", unsafe_allow_html=True)


def team_codes(snap, team):
    return [d["code"] for d in sorted(snap.get("drivers", []), key=lambda d: d.get("position") or 99) if team.lower() in str(d.get("team") or "").lower()]


def pick_focus(snap, team):
    codes = team_codes(snap, team)
    if not codes:
        return None
    wanted = st.query_params.get("driver", "HAM").upper()
    default = wanted if wanted in codes else codes[0]
    if st.session_state.get("pw_focus") not in codes:
        st.session_state["pw_focus"] = default
    return st.segmented_control("Focus driver", codes, key="pw_focus", label_visibility="collapsed") or default


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


def render(snap, team, loss, feed_note):
    kind = str((snap.get("session") or {}).get("type") or "").lower()
    if kind and kind not in RACE_TYPES:
        render_practice(snap, team, feed_note)
        return
    result = analyse(snap, team=team, pit_loss=loss)
    header(snap, result, feed_note)
    sc_banner(result)
    if not result["cars"]:
        st.warning(f"No running {team} cars in this session.")
    focus = pick_focus(snap, team)
    ordered = sorted(result["cars"], key=lambda r: r["car"]["code"] != focus)
    left, right = st.columns([3, 2])
    with left:
        for i, r in enumerate(ordered):
            if i == 0:
                driver_card(r, focus=True)
                gl.words("call", "Strategy words explained")
                teammate = ordered[1]["car"]["code"] if len(ordered) > 1 else None
                car_panel(snap, r["car"]["code"], teammate)
                st.divider()
            else:
                with st.expander(f"Teammate: P{r['car']['position']} {r['car']['code']} · {r['call']}", expanded=False):
                    driver_card(r)
    with right:
        track_map(snap, team, focus)
        radio_panel(snap, team, focus, "race")
        st.subheader("Timing")
        tower(snap, team)
        st.subheader("Race control")
        race_control(snap)
        gl.words("timing", "Timing words explained")
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


def render_practice(snap, team, feed_note):
    header(snap, None, feed_note)
    focus = pick_focus(snap, team)
    summary = practice_summary(snap, team, focus or "")
    gl.plain("This is practice, not a race. Teams test car setups and tyres, so the order here does not count. Watch the long runs: they are the best clue to Sunday's race pace.")
    left, right = st.columns([3, 2])
    with left:
        for c in summary["cars"]:
            d = c["car"]
            is_focus = d["code"] == focus
            best = f"{int(d['best_lap'] // 60)}:{d['best_lap'] % 60:06.3f}" if d.get("best_lap") else "no time yet"
            gap = f"+{c['gap_to_fastest']:.3f}s" if c["gap_to_fastest"] else ("fastest" if d.get("best_lap") else "—")
            status = "In the garage / pit lane" if d.get("in_pit") else ("Out-lap" if d.get("pit_out") else "On track")
            body = (
                f"<div class='pw-card' style='--team:{d['colour']}'><div class='pw-head'>{'⭐ ' if is_focus else ''}P{d['position']} · {d['code']} "
                f"<span class='pw-sub'>{d.get('name') or ''}</span></div>"
                f"<div class='pw-grid'>"
                f"<div><div class='pw-k'>Best lap</div><div class='pw-v'>{best}</div></div>"
                f"<div><div class='pw-k'>Gap to P1</div><div class='pw-v'>{gap}</div></div>"
                f"<div><div class='pw-k'>Laps run</div><div class='pw-v'>{d.get('laps')}</div></div>"
                f"<div><div class='pw-k'>Now</div><div class='pw-v'>{status} · {(d.get('compound') or '?')} {d.get('tyre_age')}L</div></div>"
                f"</div></div>"
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
    with right:
        st.subheader("Timing (best laps)")
        tower(snap, team)
        if len(summary["wear"]):
            st.subheader("Tyre wear from long runs (for Sunday)")
            st.dataframe(summary["wear"].rename(columns={"compound": "Tyre", "runs": "Runs", "wear_s_per_lap": "Wear s/lap", "avg_pace": "Avg lap s"}).round(3), hide_index=True)
            st.caption("Practice fuel loads are unknown, so wear here is a rough guide (burning fuel hides some wear).")
        radio_panel(snap, team, focus, "practice")
        st.subheader("Race control")
        race_control(snap)
        gl.words("practice", "Practice words explained")
    gl.flags_panel("practice")
    gl.glossary("practice")


def owner_view():
    import hmac
    import os

    key = os.environ.get("PITWALL_KEY", "")
    if not key:
        return True
    given = str(st.query_params.get("key", ""))
    return bool(given) and hmac.compare_digest(given, key)


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
    st.set_page_config(page_title="Pit Wall", page_icon="🏁", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
    from f1analytics.live.auth import load_streamlit_secrets

    load_streamlit_secrets()
    if autorecord:
        ensure_recorder()
    mode, team, loss, refresh = sidebar()
    st.title(f"{team} Pit Wall")
    rep = replay_controls() if mode == "Replay" else None
    run(mode, team, loss, refresh, rep)


def run(mode, team, loss, refresh, rep):


    @st.fragment(run_every=refresh)
    def live_view():
        snap, age = read_current()
        if snap is None:
            st.info("Connecting to F1 live timing… (on a laptop without the hosted app, run `python -m f1analytics live record`).")
            return
        snap = strip_f1tv(snap)
        feed = snap.get("feed") or {}
        status = (snap.get("session") or {}).get("status")
        note = f"Live feed {'connected' if feed.get('connected') else 'reconnecting…'} · {f1tv_badge(snap)} · updated {age:.0f}s ago · session {status or '?'}"
        if age > 30 and status not in ("Finished", "Finalised", "Ends", "Inactive"):
            st.warning(f"No update for {age:.0f}s: the feed is reconnecting or no session is running.")
        render(snap, team, loss, note)

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
        render(snap, team, loss, f"Replay · {'playing' if st.session_state.pw_play else 'paused'}")

    if mode == "Live":
        live_view()
    else:
        replay_view()
