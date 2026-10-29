import plotly.express as px
import streamlit as st

from f1analytics.analysis.laps import speed_trap
from f1analytics.ui import charts
from f1analytics.ui.state import get, session_picker, source_note

RHO_SEA = 1.225
RHO_MEXICO = 0.96


def render(ctx):
    st.subheader("Speed trap: who is fastest in a straight line")
    code = session_picker("st", "FP2", "speed")
    sd = get(ctx, code)
    if sd is None:
        return
    source_note(sd)
    data = speed_trap(sd.laps)
    if data.empty:
        st.info("No speed-trap readings in this session.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Top speed", f"{data['SpeedST'].iloc[0]:.1f} km/h", help=data["Driver"].iloc[0])
    c2.metric("Field spread", f"{data['SpeedST'].iloc[0] - data['SpeedST'].iloc[-1]:.1f} km/h")
    c3.metric("Drivers", len(data))
    left, right = st.columns([2, 1])
    fig = px.bar(data, x="Driver", y="SpeedST", color="Team", text="SpeedST")
    fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
    fig.update_yaxes(range=[data["SpeedST"].min() - 10, data["SpeedST"].max() + 5])
    left.plotly_chart(charts.style(fig, "Maximum speed-trap reading per driver", None, "km/h"), key="st_bar")
    right.dataframe(data, hide_index=True, column_config={"SpeedST": st.column_config.NumberColumn("Top speed (km/h)", format="%.1f")})
    if "mexico" in str(sd.meta.get("event_name", "")).lower():
        with st.expander("Why Mexico is so fast (altitude)"):
            st.markdown(
                f"The track sits about 2,285 m above sea level, so air density is about **{RHO_MEXICO} kg/m³** "
                f"instead of **{RHO_SEA} kg/m³** (≈{(1 - RHO_MEXICO / RHO_SEA) * 100:.0f}% thinner).\n\n"
                "Drag `F_d = ½·ρ·v²·C_d·A` and downforce `F_l = ½·ρ·v²·C_l·A` both scale with ρ, "
                "so teams run maximum-downforce wings yet still see very high top speeds."
            )
    st.caption("Uses each driver's highest speed-trap reading across all laps (the doc's version only looked at the fastest lap).")
