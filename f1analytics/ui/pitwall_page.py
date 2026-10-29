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
@media (max-width: 640px){.pw-call{font-size:1.3rem}.pw-head{font-size:1.15rem}.pw-v{font-size:1rem}}
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
    if result:
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


def car_panel(snap, focus, teammate):
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
                teammate = ordered[1]["car"]["code"] if len(ordered) > 1 else None
                car_panel(snap, r["car"]["code"], teammate)
                st.divider()
            else:
                with st.expander(f"Teammate: P{r['car']['position']} {r['car']['code']} · {r['call']}", expanded=False):
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


def render_practice(snap, team, feed_note):
    header(snap, None, feed_note)
    focus = pick_focus(snap, team)
    summary = practice_summary(snap, team, focus or "")
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
        st.subheader("Race control")
        race_control(snap)


def main(autorecord=False):
    st.set_page_config(page_title="Pit Wall", page_icon="🏁", layout="wide", initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)
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
        feed = snap.get("feed") or {}
        status = (snap.get("session") or {}).get("status")
        note = f"Live feed {'connected' if feed.get('connected') else 'reconnecting…'} · updated {age:.0f}s ago · session {status or '?'}"
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
