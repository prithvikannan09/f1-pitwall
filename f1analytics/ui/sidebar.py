from datetime import date

import streamlit as st

from f1analytics import config
from f1analytics.ui.state import SOURCE_LABELS, schedule


def render():
    st.sidebar.header("Race weekend")
    source = st.sidebar.radio(
        "Data source", list(SOURCE_LABELS), format_func=SOURCE_LABELS.get, index=0,
        help="Auto uses FastF1 if you set an F1 login, else the free OpenF1 API (2023 onwards), else sample data.",
    )
    years = list(range(date.today().year, 2017, -1))
    year = st.sidebar.selectbox("Season", years, index=years.index(config.DEFAULT_YEAR) if config.DEFAULT_YEAR in years else 0)
    sched, used = schedule(source, year)
    events = sched["EventName"].tolist()
    default = next((i for i, e in enumerate(events) if config.DEFAULT_GP.lower() in e.lower()), 0)
    gp = st.sidebar.selectbox("Grand Prix", events, index=default)
    if used == "synthetic" and source != "synthetic":
        st.sidebar.warning("No real data reachable for this season, so the calendar and data are sample data.")
    st.sidebar.divider()
    st.sidebar.caption(
        "Built from Loriane Arielle Larevoir's F1 project blueprints. "
        "Data: OpenF1 and FastF1. Estimates are labelled (est.)."
    )
    return {"source": source, "year": int(year), "gp": gp}
