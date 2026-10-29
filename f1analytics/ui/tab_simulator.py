import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from f1analytics import config
from f1analytics.simulator.monte_carlo import simulate, sweep
from f1analytics.simulator.scenario import UndercutScenario, scenario_from_session
from f1analytics.ui import charts
from f1analytics.ui.state import deg_table, get, source_note


@st.cache_data(show_spinner="Running 10,000 races…", max_entries=32)
def _run(sc):
    return simulate(sc)


@st.cache_data(show_spinner=False, max_entries=32)
def _sweeps(sc):
    return sweep(sc, "gap", np.round(np.arange(0.0, 6.01, 0.25), 2)), sweep(sc, "k", [1, 2, 3])


def render(ctx):
    st.subheader("Strategy risk simulator (Monte Carlo)")
    st.caption("Plays the same undercut 10,000 times with random pit stops, Safety Cars, traffic and lap-to-lap noise, then counts how often it works.")
    base = _from_race(ctx)
    with st.form("sim_form"):
        c1, c2, c3 = st.columns(3)
        gap = c1.number_input("Gap to car ahead (s)", value=float(max(base.gap, 0.0)), step=0.1)
        k = c1.slider("Laps rival stays out", 1, 3, int(base.k))
        pit = c1.number_input("Average pit loss (s)", value=float(base.pit_loss), step=0.5)
        fresh = c2.number_input("Fresh-tyre advantage, first lap (s)", value=float(base.fresh_delta), step=0.1)
        sc_p = c2.slider("Chance of a Safety Car this race (est.)", 0.0, 1.0, float(base.sc_prob_race), 0.05)
        vsc_p = c2.slider("Chance of a Virtual Safety Car (est.)", 0.0, 1.0, float(base.vsc_prob_race), 0.05)
        sigma = c3.number_input("Pit-stop spread, 1 σ (s, est.)", value=float(base.pit_sigma), step=0.1)
        slow = c3.slider("Chance of a slow stop (est.)", 0.0, 0.3, float(base.slow_stop_prob), 0.01)
        field_txt = c3.text_input("Gaps to cars behind you (s)", ", ".join(f"{g:g}" for g in base.field_gaps))
        submitted = st.form_submit_button("Run simulation", type="primary")
    sc = base.with_(
        gap=gap, k=k, pit_loss=pit, fresh_delta=fresh, sc_prob_race=sc_p, vsc_prob_race=vsc_p,
        pit_sigma=sigma, slow_stop_prob=slow, field_gaps=_parse(field_txt),
    )
    res = _run(sc)
    s = res.summary()
    m = st.columns(4)
    m[0].metric("Undercut works", f"{s['success_prob'] * 100:.1f}%", help=f"95% range {s['ci_low'] * 100:.1f}–{s['ci_high'] * 100:.1f}%")
    m[1].metric("Typical time gained", f"{s['gain_p50']:+.2f} s")
    m[2].metric("Bad case (5%)", f"{s['gain_p5']:+.2f} s")
    m[3].metric("Good case (95%)", f"{s['gain_p95']:+.2f} s")
    left, right = st.columns(2)
    hist = px.histogram(x=res.final_gap, nbins=60, color=np.where(res.success, "Works", "Fails"),
                        color_discrete_map={"Works": "#3DBE7A", "Fails": "#E8524A"})
    hist.add_vline(x=sc.margin, line_dash="dash")
    hist.update_layout(legend_title_text="")
    left.plotly_chart(charts.style(hist, "Final gap after both stops (below 0 = you're ahead)", "Seconds", "Simulated races", 380), key="sim_hist")
    causes = s["failure_causes"]
    bars = go.Figure(go.Bar(x=[v * 100 for v in causes.values()], y=list(causes.keys()), orientation="h", marker_color="#E8524A"))
    right.plotly_chart(charts.style(bars, "When it failed, what was going on (% of failures)", "%", None, 380), key="sim_causes")
    by_gap, by_k = _sweeps(sc)
    curve = go.Figure()
    curve.add_trace(go.Scatter(x=by_gap["gap"], y=by_gap["success_prob"] * 100, mode="lines", name="Chance it works", line=dict(color=charts.PAIR[0])))
    curve.add_trace(go.Scatter(x=list(by_gap["gap"]) + list(by_gap["gap"][::-1]), y=list(by_gap["ci_high"] * 100) + list(by_gap["ci_low"][::-1] * 100),
                               fill="toself", fillcolor="rgba(46,155,240,0.15)", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    curve.add_vline(x=sc.gap, line_dash="dot")
    st.plotly_chart(charts.style(curve, "How the chance changes with the gap", "Gap to car ahead (s)", "% of races it works", 340), key="sim_curve")
    st.dataframe(by_k.assign(success_prob=(by_k["success_prob"] * 100).round(1)).rename(columns={"k": "Laps rival stays out", "success_prob": "Works (%)", "gain_mean": "Average gain (s)"})[["Laps rival stays out", "Works (%)", "Average gain (s)"]], hide_index=True)
    with st.expander("What the model assumes"):
        st.markdown(
            f"- Pit stop = average + normal spread ({sc.pit_sigma} s) + a {sc.slow_stop_prob:.0%} chance of a slow stop adding ~{sc.slow_stop_extra:.0f} s (est.)\n"
            f"- Safety Car / VSC chance per lap = 1 − (1 − race chance)^(1/{sc.total_laps}). If one comes out while the rival is still out, the rival pits cheaply ({sc.sc_pit_factor:.0%} / {sc.vsc_pit_factor:.0%} of normal loss) and your tyre gain stops counting.\n"
            f"- If you rejoin less than {sc.clear_air:.0f} s behind another car you lose {sc.traffic_loss} s per lap until you pass ({sc.pass_prob:.0%} chance per lap).\n"
            f"- Lap noise {sc.lap_noise} s per car per lap; track grip improves ~{sc.track_evolution_mean} s/lap, which helps the rival warm tyres faster.\n"
            f"- {res.final_gap.size:,} runs keep the error on the % below ±1 point. Fixed random seed, so the same inputs give the same answer."
        )


def _from_race(ctx):
    sd = get(ctx, "R")
    with st.expander("Pre-fill from a real race moment", expanded=False):
        if sd is None:
            return UndercutScenario()
        source_note(sd)
        total = int(sd.meta.get("total_laps") or sd.laps["LapNumber"].max())
        _, models = deg_table(sd.meta["session_id"], sd.laps, total, True)
        c1, c2, c3 = st.columns(3)
        lap = c1.number_input("Lap", 2, max(total - 3, 3), min(20, max(total - 3, 3)), key="sim_lap")
        order = sd.laps[sd.laps["LapNumber"] == lap].sort_values("Position")["Driver"].tolist()
        if len(order) < 2:
            return UndercutScenario()
        target = c2.selectbox("Rival (car ahead)", order[:-1], key="sim_target")
        attacker = order[order.index(target) + 1]
        c3.markdown(f"**You:** {attacker} (the car right behind)")
        use = st.toggle("Use this race moment", value=False, key="sim_use")
        if not use:
            return UndercutScenario(total_laps=total)
        try:
            sc, info = scenario_from_session(sd, attacker, target, lap, models)
        except LookupError as exc:
            st.warning(str(exc))
            return UndercutScenario(total_laps=total)
        st.caption(f"Rival on {info['target_compound']} aged {info['target_tyre_age']:.0f} laps; you switch to {info['new_compound']}. Gap {sc.gap:.2f} s.")
        return sc


def _parse(text):
    vals = []
    for part in text.replace(";", ",").split(","):
        try:
            v = float(part)
        except ValueError:
            continue
        if v > 0:
            vals.append(v)
    return tuple(vals) if vals else ()
