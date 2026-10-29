import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from f1analytics.analysis.weather import pace_vs_track_temp, weather_trend
from f1analytics.ui import charts
from f1analytics.ui.state import get, session_picker, source_note


def render(ctx):
    st.subheader("Weather and track conditions")
    code = session_picker("wx", "R", "wx")
    sd = get(ctx, code)
    if sd is None:
        return
    source_note(sd)
    wx = weather_trend(sd.weather)
    if wx.empty:
        st.info("No weather data for this session.")
        return
    m = st.columns(4)
    m[0].metric("Track temp", f"{wx['TrackTemp'].iloc[-1]:.1f} °C", f"{wx['TrackTemp'].iloc[-1] - wx['TrackTemp'].iloc[0]:+.1f} over session")
    m[1].metric("Air temp", f"{wx['AirTemp'].iloc[-1]:.1f} °C")
    m[2].metric("Humidity", f"{wx['Humidity'].iloc[-1]:.0f}%")
    m[3].metric("Rain", "Yes" if wx["Rainfall"].any() else "No")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, subplot_titles=("Temperature (°C)", "Humidity (%) and wind (m/s)"))
    fig.add_trace(go.Scatter(x=wx["Minutes"], y=wx["TrackTempSmooth"], name="Track", line=dict(color="#E8524A")), 1, 1)
    fig.add_trace(go.Scatter(x=wx["Minutes"], y=wx["AirTempSmooth"], name="Air", line=dict(color="#2E9BF0")), 1, 1)
    fig.add_trace(go.Scatter(x=wx["Minutes"], y=wx["HumiditySmooth"], name="Humidity", line=dict(color="#9C6ADE")), 2, 1)
    fig.add_trace(go.Scatter(x=wx["Minutes"], y=wx["WindSpeedSmooth"], name="Wind", line=dict(color="#3DBE7A")), 2, 1)
    rain = wx[wx["Rainfall"]]
    if not rain.empty:
        fig.add_trace(go.Scatter(x=rain["Minutes"], y=rain["TrackTemp"], mode="markers", name="Rain", marker=dict(symbol="triangle-down", size=9, color="#0067AD")), 1, 1)
    fig.update_xaxes(title_text="Minutes into session", row=2, col=1)
    st.plotly_chart(charts.style(fig, height=520), key="wx_fig")
    total = int(sd.meta.get("total_laps") or 0) or int(sd.laps["LapNumber"].max())
    merged, fit = pace_vs_track_temp(sd.laps, sd.weather, total, sd.is_race)
    if fit:
        sc = px.scatter(merged, x="TrackTemp", y="Residual", color="Compound", opacity=0.5,
                        color_discrete_map={"SOFT": "#FF3333", "MEDIUM": "#FFF200", "HARD": "#EBEBEB"})
        lo, hi = merged["TrackTemp"].min(), merged["TrackTemp"].max()
        sc.add_trace(go.Scatter(x=[lo, hi], y=[fit["intercept"] + fit["slope_s_per_c"] * lo, fit["intercept"] + fit["slope_s_per_c"] * hi], mode="lines", name="Trend", line=dict(color="#B0B0B0", dash="dash")))
        st.plotly_chart(charts.style(sc, "Lap time vs track temperature (each lap compared with the driver's stint average)", "Track temp (°C)", "Seconds vs stint average", 380), key="wx_scatter")
        st.caption(f"Trend: {fit['slope_s_per_c']:+.3f} s per °C (r² {fit['r2']:.2f}, {fit['n']} laps). A weak r² means temperature is not the main driver here.")
