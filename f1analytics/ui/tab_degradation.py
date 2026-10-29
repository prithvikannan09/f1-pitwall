import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from f1analytics import config
from f1analytics.analysis.fuel import fuel_corrected, fuel_gain_per_lap
from f1analytics.analysis.laps import clean_laps, estimate_pit_loss, seconds
from f1analytics.analysis.pit_window import best_per_strategy, one_stop_optimum, optimise, pit_window
from f1analytics.ui import charts
from f1analytics.ui.state import deg_table, get, session_picker, source_note


def render(ctx):
    st.subheader("Tyre degradation and pit-window optimiser")
    code = session_picker("deg", "R", "deg")
    sd = get(ctx, code)
    if sd is None:
        return
    source_note(sd)
    total = int(sd.meta.get("total_laps") or sd.laps["LapNumber"].max())
    clean = clean_laps(sd.laps)
    if clean.empty:
        st.info("No clean laps to analyse.")
        return
    box = clean.assign(LapTimeSeconds=seconds(clean["LapTime"]))
    fig = px.box(box, x="Compound", y="LapTimeSeconds", color="Compound", color_discrete_map=config.COMPOUND_COLORS, points="outliers")
    st.plotly_chart(charts.style(fig, "Clean lap times by compound (no Safety Car, pit or lap-1 laps)", None, "Lap time (s)"), key="deg_box")
    stints, models = deg_table(sd.meta["session_id"], sd.laps, total, sd.is_race)
    if stints.empty:
        st.info("Not enough long stints (5+ clean laps) to fit degradation.")
        return
    if sd.is_race:
        st.markdown(
            f"**Fuel correction** (race only): lap time − k·fuel, fuel = F₀·(1 − (lap−1)/N). "
            f"With F₀ = {config.START_FUEL_KG:.0f} kg (est.) and k = {config.FUEL_SEC_PER_KG} s/kg (est.), burning fuel makes the car "
            f"**{fuel_gain_per_lap(total):.3f} s/lap** faster, which would otherwise hide tyre wear."
        )
    else:
        st.caption("Practice/qualifying fuel loads are unknown, so these slopes are not fuel-corrected.")
    summary = stints.groupby("Compound").agg(stints=("beta", "size"), wear_s_per_lap=("beta", "median"), new_tyre_pace_s=("alpha", "median")).reset_index()
    c1, c2 = st.columns([1, 2])
    c1.dataframe(summary, hide_index=True, column_config={
        "wear_s_per_lap": st.column_config.NumberColumn("Wear (s/lap)", format="%.3f"),
        "new_tyre_pace_s": st.column_config.NumberColumn("New-tyre pace (s)", format="%.2f"),
    })
    driver = c2.selectbox("Show a driver's stints", sorted(stints["Driver"].unique()), key="deg_driver")
    c2.plotly_chart(_stint_fig(sd, stints, driver, total), key="deg_stints")
    st.markdown("#### Best strategy for this race")
    p1, p2 = st.columns(2)
    pit_loss = p1.number_input("Pit-stop time loss (s)", value=round(estimate_pit_loss(sd.laps), 1), step=0.5, key="deg_pitloss",
                               help="Estimated from this session's in-laps and out-laps.")
    laps_total = p2.number_input("Race distance (laps)", value=total, step=1, key="deg_total")
    if len(models) < 2:
        st.info("Need degradation for at least two dry compounds to compare strategies.")
        return
    plans = optimise(int(laps_total), pit_loss, models)
    best = best_per_strategy(plans).head(8)
    best = best.assign(pit_laps=best["pit_laps"].apply(lambda t: ", ".join(map(str, t))), delta=best["delta"].round(2))
    st.dataframe(best[["stops", "compounds", "pit_laps", "delta"]], hide_index=True, column_config={
        "pit_laps": "Pit on lap(s)", "delta": st.column_config.NumberColumn("Slower than best by (s)", format="%.2f"),
    })
    one = plans[plans["stops"] == 1]
    if not one.empty:
        top = one.iloc[0]["compounds"]
        win = pit_window(plans, top)
        c_a, c_b = top.split("-")
        laps_opt = one_stop_optimum(*models[c_a], *models[c_b], int(laps_total))
        st.success(
            f"Best one-stop: **{top}**, pit on lap **{win.iloc[0]['pit_laps'][0]}–{win.iloc[-1]['pit_laps'][0]}** "
            f"(within {config.PIT_WINDOW_TOLERANCE_S:.0f} s of ideal; formula optimum lap {laps_opt:.1f})."
        )
        curve = one[one["compounds"] == top]
        fig = go.Figure(go.Scatter(x=[p[0] for p in curve["pit_laps"]], y=curve["delta"], mode="lines", line=dict(color=charts.PAIR[0])))
        fig.add_hrect(y0=0, y1=config.PIT_WINDOW_TOLERANCE_S, fillcolor="green", opacity=0.15, line_width=0)
        st.plotly_chart(charts.style(fig, f"{top}: time lost vs the ideal pit lap", "Pit lap", "Seconds slower", 320), key="deg_window")
    with st.expander("How the optimiser works"):
        st.markdown(
            "Each compound gets a line: lap time = α + β·tyre age (α = new-tyre pace, β = wear per lap).\n\n"
            "A stint of L laps costs `L·α + β·(L + L(L−1)/2)`. Every 1- and 2-stop plan with at least two "
            "dry compounds and stints of 8+ laps is added up, plus pit loss per stop, and the fastest wins. "
            "Fuel is the same for every plan, so it cancels out."
        )


def _stint_fig(sd, stints, driver, total):
    rows = clean_laps(sd.laps)
    rows = rows[rows["Driver"] == driver]
    rows = fuel_corrected(rows, total) if sd.is_race else rows.assign(FuelCorrected=seconds(rows["LapTime"]))
    fig = go.Figure()
    for _, s in stints[stints["Driver"] == driver].iterrows():
        pts = rows[rows["Stint"] == s["Stint"]]
        color = charts.compound_color(s["Compound"])
        fig.add_trace(go.Scatter(x=pts["LapNumber"], y=pts["FuelCorrected"], mode="markers", marker=dict(color=color, size=6), name=f"Stint {int(s['Stint'])} {s['Compound']}"))
        life = np.linspace(s["first_life"], s["last_life"], 10)
        lap0 = pts["LapNumber"].min() - pts["TyreLife"].min()
        fig.add_trace(go.Scatter(x=lap0 + life, y=s["alpha"] + s["beta"] * life, mode="lines", line=dict(color=color, dash="dash"), name=f"{s['beta']:.3f} s/lap"))
    label = "Fuel-corrected lap time (s)" if sd.is_race else "Lap time (s)"
    return charts.style(fig, f"{driver}: lap time vs lap, with fitted wear", "Lap", label, 360)
