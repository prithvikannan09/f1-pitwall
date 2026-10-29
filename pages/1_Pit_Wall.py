import warnings
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from f1analytics.live.recorder import LIVE_DIR, read_current
from f1analytics.live.replay import RaceReplay, load_fixture, load_openf1_race
from f1analytics.pitwall.engine import analyse
from f1analytics.ui import charts

warnings.filterwarnings("ignore")
st.set_page_config(page_title="Pit Wall", page_icon="🏁", layout="wide")

BUNDLED = Path(__file__).resolve().parent.parent / "f1analytics" / "replays" / "usgp2026"
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

st.markdown("""
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
.pw-banner{border-radius:10px;padding:12px 16px;font-weight:700;margin:8px 0;color:#111}
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Loading race for replay…", max_entries=4)
def get_replay(kind, year, gp):
    if kind == "bundled":
        return RaceReplay(load_fixture(BUNDLED))
    return RaceReplay(load_openf1_race(int(year), gp))


def sidebar():
    st.sidebar.header("Pit wall")
    mode = st.sidebar.radio("Mode", ["Live", "Replay"], index=0, help="Live reads the recorder running in your terminal. Replay steps through a past race lap by lap.")
    team = st.sidebar.selectbox("Team", ["Ferrari", "McLaren", "Mercedes", "Red Bull", "Aston Martin", "Williams", "Alpine", "Haas", "Racing Bulls", "Audi", "Cadillac"], index=0)
    loss = st.sidebar.number_input("Pit-stop time loss override (s)", min_value=0.0, max_value=40.0, value=0.0, step=0.5,
                                   help="0 = automatic: measured from this race's stops once 3+ have happened, otherwise a track default (est.).")
    refresh = st.sidebar.slider("Refresh every (s)", 2, 15, 3)
    return mode, team, (loss or None), refresh


def replay_controls():
    st.sidebar.divider()
    st.sidebar.subheader("Replay")
    choice = st.sidebar.radio("Race", ["2026 US GP (bundled, works offline)", "Pick a race (OpenF1)"], index=0)
    if choice.startswith("2026 US"):
        kind, year, gp = "bundled", 2026, "Austin"
    else:
        kind = "openf1"
        year = st.sidebar.number_input("Season", 2023, 2026, 2025)
        gp = st.sidebar.text_input("Grand Prix (name or city)", "Mexico")
    try:
        rep = get_replay(kind, year, gp)
    except Exception as exc:
        st.error(f"Could not load that race: {exc}")
        return None
    st.session_state.setdefault("pw_play", False)
    st.session_state.setdefault("pw_lap", 1)
    c1, c2 = st.sidebar.columns(2)
    if c1.button("▶ Play" if not st.session_state.pw_play else "⏸ Pause", width="stretch"):
        st.session_state.pw_play = not st.session_state.pw_play
    if c2.button("⏮ Lap 1", width="stretch"):
        st.session_state.pw_lap = 1
    st.session_state.pw_lap = min(max(int(st.session_state.pw_lap), 1), rep.total_laps)
    return rep


def header(snap, result, feed_note):
    s = snap["session"]
    label, colour = STATUS_STYLE.get(result["track_status"], (f"STATUS {result['track_status']}", "#888"))
    st.markdown(
        f"<span class='pw-pill' style='background:{colour};color:#111'>{label}</span>"
        f"<span class='pw-pill' style='background:#1F2937;color:#fff'>LAP {s.get('lap') or 0} / {result['total_laps']}</span>"
        f"<span class='pw-pill' style='background:#1F2937;color:#fff'>{s.get('meeting') or ''} · {s.get('name') or ''}</span>"
        f"<span class='pw-sub'>{feed_note}</span>",
        unsafe_allow_html=True,
    )
    st.caption(f"Pit-stop loss used: **{result['pit_loss']:.1f} s** ({result['pit_loss_source']}).")


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


def driver_card(r):
    car = r["car"]
    bg, fg = CALL_STYLE.get(r["call"], ("#374151", "#FFF"))
    with st.container(border=False):
        st.markdown(
            f"<div class='pw-card' style='--team:{car['colour']}'><div class='pw-head'>P{car['position']} · {car['code']} "
            f"<span class='pw-sub'>{car.get('name') or ''}</span></div>"
            f"<div class='pw-call' style='background:{bg};color:{fg}'>{r['call']}</div>"
            f"<div class='pw-why'>{r['why']}</div></div>",
            unsafe_allow_html=True,
        )
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
    rows = []
    for d in sorted([d for d in snap["drivers"] if d.get("position")], key=lambda d: d["position"]):
        rows.append({
            "P": d["position"], "Driver": d["code"], "Team": d.get("team"),
            "Gap": "OUT" if d.get("retired") else ("Leader" if d["position"] == 1 else fmt_gap(d.get("gap_to_leader"), d.get("laps_down"))),
            "Int": fmt_gap(d.get("interval"), d.get("interval_laps")) if d["position"] > 1 and not d.get("retired") else "",
            "Tyre": f"{(d.get('compound') or '?')[:1]} {d.get('tyre_age')}",
            "Stops": d.get("stops"), "Last": f"{d['last_lap']:.3f}" if d.get("last_lap") else "",
            "Pit": "IN" if d.get("in_pit") else ("OUT" if d.get("pit_out") else ""),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("No timing yet.")
        return
    mine = df["Team"].fillna("").str.contains(team, case=False)
    st.dataframe(df.style.apply(lambda r: ["background-color: rgba(225,6,0,0.25)" if mine[r.name] else "" for _ in r], axis=1),
                 hide_index=True, height=min(38 * (len(df) + 1), 820))


def race_control(snap):
    msgs = list(reversed(snap.get("race_control") or []))[:8]
    for m in msgs:
        st.markdown(f"<span class='pw-sub'>Lap {m.get('lap') or '–'}</span> {m.get('message')}", unsafe_allow_html=True)


def render(snap, team, loss, feed_note):
    result = analyse(snap, team=team, pit_loss=loss)
    header(snap, result, feed_note)
    sc_banner(result)
    if not result["cars"]:
        st.warning(f"No running {team} cars in this session.")
    left, right = st.columns([3, 2])
    with left:
        cols = st.columns(max(len(result["cars"]), 1))
        for col, r in zip(cols, result["cars"]):
            with col:
                driver_card(r)
    with right:
        st.subheader("Timing")
        tower(snap, team)
        st.subheader("Race control")
        race_control(snap)
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


mode, team, loss, refresh = sidebar()
st.title(f"{team} Pit Wall")
rep = replay_controls() if mode == "Replay" else None


@st.fragment(run_every=refresh)
def live_view():
    snap, age = read_current()
    if snap is None:
        st.info("Waiting for the live feed. In a terminal run:  `python -m f1analytics live record`  (start it before the session).")
        return
    feed = snap.get("feed") or {}
    note = f"Live feed {'connected' if feed.get('connected') else 'reconnecting…'} · updated {age:.0f}s ago"
    if age > 20:
        st.warning(f"No update for {age:.0f}s. Is the recorder still running? (`python -m f1analytics live record`)")
    render(snap, team, loss, note)


@st.fragment(run_every=refresh)
def replay_view():
    if rep is None:
        return
    if st.session_state.pw_play and st.session_state.pw_lap < rep.total_laps:
        st.session_state.pw_lap += 1
    lap = st.slider("Lap", 1, rep.total_laps, key="pw_lap")
    snap = rep.snapshot(lap)
    render(snap, team, loss, f"Replay · {'playing' if st.session_state.pw_play else 'paused'}")


if mode == "Live":
    live_view()
else:
    replay_view()
