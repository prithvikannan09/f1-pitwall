import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from f1analytics.analysis.laps import fastest_lap_per_driver
from f1analytics.analysis.telemetry import distance_delta, lap_summary
from f1analytics.ui import charts
from f1analytics.ui.state import get, session_picker, source_note, telemetry


def render(ctx):
    st.subheader("Telemetry overlay and lap delta")
    code = session_picker("tel", "Q", "tel")
    sd = get(ctx, code)
    if sd is None:
        return
    source_note(sd)
    ranking = fastest_lap_per_driver(sd.laps)
    drivers = ranking["Driver"].tolist()
    if len(drivers) < 2:
        st.info("Need at least two drivers with timed laps.")
        return
    c1, c2 = st.columns(2)
    d1 = c1.selectbox("Driver 1", drivers, index=0, key="tel_d1")
    d2 = c2.selectbox("Driver 2", drivers, index=1, key="tel_d2")
    try:
        t1 = telemetry(ctx["source"], ctx["year"], ctx["gp"], code, d1)
        t2 = telemetry(ctx["source"], ctx["year"], ctx["gp"], code, d2)
    except Exception as exc:
        st.error(f"Telemetry not available: {exc}")
        return
    lap1 = ranking.loc[ranking["Driver"] == d1, "LapTimeSeconds"].iloc[0]
    lap2 = ranking.loc[ranking["Driver"] == d2, "LapTimeSeconds"].iloc[0]
    s1, s2 = lap_summary(t1), lap_summary(t2)
    m = st.columns(4)
    m[0].metric(f"{d1} fastest lap", _fmt(lap1))
    m[1].metric(f"{d2} fastest lap", _fmt(lap2), delta=f"{lap2 - lap1:+.3f} s", delta_color="inverse")
    m[2].metric("Top speed", f"{s1['top_speed']:.0f} / {s2['top_speed']:.0f} km/h")
    m[3].metric("Full throttle", f"{s1['full_throttle_pct']:.0f}% / {s2['full_throttle_pct']:.0f}%")
    delta = distance_delta(t1, t2)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.4, 0.2, 0.15, 0.25],
                        subplot_titles=("Speed (km/h)", "Throttle (%)", "Brake", f"Gap: {d2} vs {d1} (s, above 0 = {d2} behind)"))
    for tel, name, color in ((t1, d1, charts.PAIR[0]), (t2, d2, charts.PAIR[1])):
        fig.add_trace(go.Scatter(x=tel["Distance"], y=tel["Speed"], name=name, line=dict(color=color, width=1.6), legendgroup=name), 1, 1)
        fig.add_trace(go.Scatter(x=tel["Distance"], y=tel["Throttle"], name=name, line=dict(color=color, width=1.2), legendgroup=name, showlegend=False), 2, 1)
        fig.add_trace(go.Scatter(x=tel["Distance"], y=tel["Brake"].astype(int), name=name, line=dict(color=color, width=1.2, shape="hv"), legendgroup=name, showlegend=False), 3, 1)
    fig.add_trace(go.Scatter(x=delta["Distance"], y=delta["Delta"], name="Gap", line=dict(color="#B0B0B0", width=1.6), fill="tozeroy", showlegend=False), 4, 1)
    fig.update_xaxes(title_text="Distance along the lap (m)", row=4, col=1)
    st.plotly_chart(charts.style(fig, height=760), key="tel_fig")
    st.caption("The gap line is built from both drivers' time at the same point on track: where it climbs, the second driver is losing time.")


def _fmt(seconds):
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:06.3f}"
