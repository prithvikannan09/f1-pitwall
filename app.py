import warnings

import streamlit as st

from f1analytics.ui import (
    sidebar, tab_database, tab_degradation, tab_race_pace, tab_simulator,
    tab_speed_trap, tab_telemetry, tab_undercut, tab_weather,
)

warnings.filterwarnings("ignore", category=FutureWarning)
st.set_page_config(page_title="F1 Race Engineering Command Centre", page_icon="🏁", layout="wide")

ctx = sidebar.render()
st.title("F1 Race Engineering Command Centre")
st.caption(f"{ctx['year']} {ctx['gp']} · telemetry, tyre strategy and race-day risk in one place")

TABS = [
    ("Speed Trap", tab_speed_trap),
    ("Telemetry", tab_telemetry),
    ("Tyre Degradation", tab_degradation),
    ("Undercut Calculator", tab_undercut),
    ("Strategy Simulator", tab_simulator),
    ("Weather", tab_weather),
    ("Race Pace", tab_race_pace),
    ("Database", tab_database),
]

for (label, module), tab in zip(TABS, st.tabs([t[0] for t in TABS])):
    with tab:
        try:
            module.render(ctx)
        except Exception as exc:
            st.error(f"{label} hit a problem: {exc}")
