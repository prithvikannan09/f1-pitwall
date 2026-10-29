import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from f1analytics.analysis.laps import lap_time_matrix, race_gaps
from f1analytics.ui import charts
from f1analytics.ui.state import get, session_picker, source_note


def render(ctx):
    st.subheader("Race pace and lap deltas")
    code = session_picker("rp", "R", "rp")
    sd = get(ctx, code)
    if sd is None:
        return
    source_note(sd)
    if not sd.is_race:
        st.info("Gaps between cars only make sense in a race or sprint. Pick Race above.")
        return
    final = sd.laps.sort_values("LapNumber").groupby("Driver").tail(1).sort_values(["LapNumber", "Position"], ascending=[False, True])
    order = final["Driver"].tolist()
    ref = st.selectbox("Compare everyone with", order, index=0, key="rp_ref")
    chosen = st.multiselect("Drivers", order, default=order[:6], key="rp_drivers")
    gaps = race_gaps(sd.laps, ref)
    fig = go.Figure()
    for d in chosen:
        if d in gaps:
            fig.add_trace(go.Scatter(x=gaps.index, y=gaps[d], name=d, mode="lines"))
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(charts.style(fig, f"Gap to {ref} (s), higher on the chart = further ahead", "Lap", "Seconds behind", 460), key="rp_gaps")
    matrix = lap_time_matrix(sd.laps)
    if not matrix.empty:
        rel = matrix.sub(matrix.median(axis=0), axis=1).reindex([d for d in order if d in matrix.index])
        heat = px.imshow(rel, color_continuous_scale="RdBu_r", zmin=-1.5, zmax=1.5, aspect="auto",
                         labels=dict(x="Lap", y="Driver", color="s vs median"))
        st.plotly_chart(charts.style(heat, "Lap time vs the field's median for that lap (blue = faster)", height=560), key="rp_heat")
        st.caption("Only clean laps are shown: Safety Car, pit and lap-1 laps are blank.")
