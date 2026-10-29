import streamlit as st

from f1analytics.analysis.degradation import compound_models, fit_stints
from f1analytics.sources import SessionKey, load_with_fallback, schedule_with_fallback

SOURCE_LABELS = {
    "auto": "Auto: real data if online",
    "openf1": "Real data: OpenF1 (free, 2023+)",
    "fastf1": "Real data: FastF1 (needs F1 login)",
    "synthetic": "Sample data (works offline)",
}
SESSION_LABELS = {
    "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3",
    "SQ": "Sprint Qualifying", "S": "Sprint", "Q": "Qualifying", "R": "Race",
}


@st.cache_resource(max_entries=8, show_spinner="Loading session data…")
def load_session(source_mode, year, gp, code):
    return load_with_fallback(SessionKey(int(year), gp, code), mode=source_mode)


@st.cache_data(show_spinner=False)
def schedule(source_mode, year):
    return schedule_with_fallback(int(year), mode=source_mode)


@st.cache_data(show_spinner="Loading telemetry…", max_entries=64)
def telemetry(source_mode, year, gp, code, driver, lap=-1):
    return load_session(source_mode, year, gp, code).telemetry(driver, lap)


@st.cache_data(show_spinner=False, max_entries=16)
def deg_table(session_id, _laps, total_laps, is_race):
    stints = fit_stints(_laps, total_laps, is_race)
    return stints, compound_models(stints)


def session_picker(label_key, default, key):
    codes = list(SESSION_LABELS)
    return st.selectbox(
        "Session", codes, index=codes.index(default),
        format_func=lambda c: SESSION_LABELS[c], key=f"{key}_{label_key}",
    )


def get(ctx, code):
    try:
        return load_session(ctx["source"], ctx["year"], ctx["gp"], code)
    except Exception as exc:
        st.error(f"Could not load {SESSION_LABELS.get(code, code)}: {exc}")
        return None


def source_note(sd):
    if sd is None:
        return
    src = sd.meta.get("data_source")
    if src == "synthetic":
        st.caption("⚠️ Sample data: realistic but not the real session (no real data reachable for this pick, or sample mode chosen).")
    else:
        st.caption(f"Real session data from {'OpenF1' if src == 'openf1' else 'FastF1 (official F1 timing)'}.")
