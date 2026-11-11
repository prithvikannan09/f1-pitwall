import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from f1analytics.pitwall import duel
from f1analytics.ui.mobile import how

FONT = dict(family="Michroma, sans-serif", color="#F3F3F5", size=11)
KIND_HELP = {
    "Start and lap 1": "Places made or lost at the start and on the first lap.",
    "Racing laps": "Normal green-flag laps: pure pace, tyres and traffic.",
    "Pit stops": "Laps where either driver came in or went out of the pits.",
    "Safety car and VSC laps": "Laps under a Safety Car or Virtual Safety Car, where the gap shrinks or grows by timing luck.",
}


def _chart(fig, height=320):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), font=FONT, paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    fig.update_xaxes(gridcolor="#2E2E3A", zeroline=False)
    fig.update_yaxes(gridcolor="#2E2E3A", zeroline=False)
    return fig


@st.cache_data(ttl=7 * 86400, show_spinner="Loading telemetry from OpenF1…", max_entries=40)
def lap_telemetry(session_key, num, t0_iso, t1_iso):
    from f1analytics.sources.openf1_source import OpenF1Source

    src = OpenF1Source(timeout=25, retries=3)
    kw = {"date>": t0_iso, "date<": t1_iso}
    car = src._get("car_data", session_key=int(session_key), driver_number=int(num), **kw)
    loc = src._get("location", session_key=int(session_key), driver_number=int(num), **kw)
    return car, loc


def _lap_row(laps, num, lap):
    r = laps[(laps["driver_number"] == num) & (laps["lap_number"] == lap)]
    return r.iloc[0] if len(r) else None


def _fastest(laps, num):
    x = laps[(laps["driver_number"] == num) & laps["clean"]].dropna(subset=["lap_duration"])
    if x.empty:
        x = laps[laps["driver_number"] == num].dropna(subset=["lap_duration"])
    return None if x.empty else int(x.sort_values("lap_duration").iloc[0]["lap_number"])


def _trace_for(sk, row, num):
    t0, t1 = duel.lap_window(row, pad=1.0)
    car, loc = lap_telemetry(sk, num, t0.isoformat(), t1.isoformat())
    w0, w1 = duel.lap_window(row)
    secs = [row.get("duration_sector_1"), row.get("duration_sector_2"), row.get("duration_sector_3")]
    return duel.trace(car, loc, w0, w1, row["lap_duration"], secs)


def _fmt(sec):
    m, s = divmod(float(sec), 60)
    return f"{int(m)}:{s:06.3f}"


def gap_section(laps, a, b, ca, cb, col_a, col_b):
    g = duel.gap_breakdown(laps, a, b)
    if not g:
        st.caption("Not enough laps in common to split the gap.")
        return
    fin = g["final_gap"]
    ahead, behind = (cb, ca) if fin < 0 else (ca, cb)
    st.markdown(f"<div class='duel-head'><b>{ahead}</b> was <b>{abs(fin):.1f}s</b> ahead of <b>{behind}</b> after lap {g['last_lap']}. "
                f"Here is where that gap came from.</div>", unsafe_allow_html=True)
    bk = g["buckets"].copy()
    gains = -bk["sum"]
    fig = go.Figure(go.Bar(
        y=list(bk.index), x=list(gains), orientation="h",
        marker_color=[col_b if v > 0 else col_a for v in gains],
        text=[f"{cb if v > 0 else ca} +{abs(v):.1f}s" for v in gains], textposition="auto",
        hovertext=[f"{KIND_HELP.get(k, '')} ({int(n)} laps)" for k, n in zip(bk.index, bk["count"])], hoverinfo="text"))
    fig.update_layout(xaxis_title=f"seconds gained ← {ca} · {cb} →")
    st.plotly_chart(_chart(fig, 230), use_container_width=True, config={"displayModeBar": False})
    lines = []
    for kind, row in bk.iterrows():
        v = -row["sum"]
        if abs(v) < 0.05:
            continue
        who = cb if v > 0 else ca
        extra = ""
        if kind == "Racing laps" and row["count"]:
            extra = f", about {abs(v) / row['count']:.2f}s a lap over {int(row['count'])} laps"
        lines.append(f"<li><b>{kind}:</b> {who} gained {abs(v):.1f}s{extra}. <span class='duel-dim'>{KIND_HELP.get(kind, '')}</span></li>")
    st.markdown("<ul class='duel-list'>" + "".join(lines) + "</ul>", unsafe_allow_html=True)
    df = g["laps"]
    fig = go.Figure(go.Scatter(x=df["lap"], y=-df["gap"], mode="lines", line=dict(color=col_b, width=2),
                               hovertemplate="Lap %{x}: %{y:+.1f}s<extra></extra>", name=f"{cb} ahead (+) / {ca} ahead (−)"))
    fig.add_hline(y=0, line_color="#55556A", line_dash="dot")
    fig.update_layout(xaxis_title="Lap", yaxis_title=f"{cb} ahead by (s)", showlegend=False)
    st.plotly_chart(_chart(fig, 240), use_container_width=True, config={"displayModeBar": False})


def _strip(stints, total, colour_line):
    segs = ""
    for st_ in stints:
        end = st_["end"] or total
        w = (end - st_["start"] + 1) / max(total, 1) * 100
        c = duel.COMPOUND_COLOUR.get(st_["compound"], "#9A9AA8")
        txt = "#15151E" if st_["compound"] in ("MEDIUM", "HARD") else "#FFFFFF"
        segs += (f"<div class='ty-seg' style='width:{w:.2f}%;background:{c};color:{txt}' title='{st_['compound'].title()} laps {st_['start']}–{end}'>"
                 f"{duel.COMPOUND_SHORT.get(st_['compound'], '?')} {st_['start']}–{end}</div>")
    return f"<div class='ty-bar' style='border-left:4px solid {colour_line}'>{segs}</div>"


def tyre_section(raw, laps, a, b, ca, cb, col_a, col_b):
    st.markdown("#### Tyres and wear")
    total = int(laps["lap_number"].max()) if len(laps) else 0
    sa, sb = duel.stints_for(raw, a), duel.stints_for(raw, b)
    if not sa or not sb:
        st.caption("No tyre data for one of the drivers.")
        return
    st.markdown(f"<div class='ty-row'><span class='ty-name'>{ca}</span>{_strip(sa, total, col_a)}</div>"
                f"<div class='ty-row'><span class='ty-name'>{cb}</span>{_strip(sb, total, col_b)}</div>", unsafe_allow_html=True)
    rows = ""
    for code, num, stints in ((ca, a, sa), (cb, b, sb)):
        for i, st_ in enumerate(stints, 1):
            w = duel.stint_wear(laps, num, st_, total)
            wear = "–" if w["wear"] is None else f"{w['wear']:+.3f}s"
            pace = "–" if w["pace"] is None else _fmt(w["pace"])
            note = ""
            if w["wear"] is not None:
                note = "got faster (track improving)" if w["wear"] < -0.02 else ("held on well" if w["wear"] < 0.08 else "dropped off")
            dot = f"<i class='ty-dot' style='background:{duel.COMPOUND_COLOUR.get(st_['compound'], '#9A9AA8')}'></i>"
            used = f" (used, {st_['age0']} laps old)" if st_["age0"] else ""
            rows += (f"<tr><td>{code}</td><td>{i}</td><td>{dot}{st_['compound'].title()}{used}</td><td>{st_['start']}–{st_['end'] or total}</td>"
                     f"<td>{pace}</td><td>{wear}</td><td class='duel-dim'>{note}</td></tr>")
    st.markdown(f"<table class='duel-t'><tr><th>Driver</th><th>Stint</th><th>Tyre</th><th>Laps</th><th>Typical lap</th><th>Wear per lap</th><th></th></tr>{rows}</table>",
                unsafe_allow_html=True)
    fpl = duel.fuel_per_lap(total)
    how(f"Wear per lap = how much slower each lap got on that set, after removing the fuel effect (cars get about {fpl:.3f}s a lap faster as fuel burns; "
               "assumption from the app's fuel model). Minus means the laps got quicker, usually because the track was drying or rubbering in. "
               "Typical lap = median of that stint's laps, leaving out pit laps and Safety Car laps.")
    fig = go.Figure()
    for code, num, colr in ((ca, a, col_a), (cb, b, col_b)):
        x = laps[(laps["driver_number"] == num) & ~laps["pit_in"].astype(bool) & ~laps["pit_out"].astype(bool)].dropna(subset=["lap_duration"])
        med = x["lap_duration"].median()
        x = x[x["lap_duration"] < med * 1.25]
        fig.add_trace(go.Scatter(x=x["lap_number"], y=x["lap_duration"], mode="lines+markers", name=code, line=dict(color=colr, width=1.6),
                                 marker=dict(size=6, color=[duel.COMPOUND_COLOUR.get(str(c).upper(), "#9A9AA8") for c in x["compound"]],
                                             line=dict(color=colr, width=1)),
                                 hovertemplate=f"{code} lap %{{x}}: %{{y:.3f}}s<extra></extra>"))
    fig.update_layout(xaxis_title="Lap", yaxis_title="Lap time (s)")
    st.plotly_chart(_chart(fig, 300), use_container_width=True, config={"displayModeBar": False})
    how("Dot colour = tyre: red soft, yellow medium, white hard, green intermediate, blue wet. Pit laps and very slow laps are left out.")
    traps_a, traps_b = duel.speed_traps(raw.get("laps"), a), duel.speed_traps(raw.get("laps"), b)
    if len(traps_a) and len(traps_b) and "st_speed" in traps_a:
        st.markdown("#### Speeds through the race")
        names = {"st_speed": "Speed trap (fastest point)", "i1_speed": "Intermediate 1", "i2_speed": "Intermediate 2"}
        cols = [c for c in names if c in traps_a]
        m = st.columns(len(cols))
        for col, c in zip(m, cols):
            va, vb = traps_a[c].median(), traps_b[c].median()
            ma, mb = traps_a[c].max(), traps_b[c].max()
            col.markdown(f"<div class='duel-k'>{names[c]}</div><div class='duel-v'>{ca} {va:.0f} · {cb} {vb:.0f}</div>"
                         f"<div class='duel-dim' style='font-size:.7rem'>Typical km/h · best {ca} {ma:.0f}, {cb} {mb:.0f}</div>", unsafe_allow_html=True)
        fig = go.Figure()
        for code, t, colr in ((ca, traps_a, col_a), (cb, traps_b, col_b)):
            fig.add_trace(go.Scatter(x=t["lap_number"], y=t["st_speed"], mode="lines", name=code, line=dict(color=colr, width=1.6),
                                     hovertemplate=f"{code} lap %{{x}}: %{{y:.0f}} km/h<extra></extra>"))
        fig.update_layout(xaxis_title="Lap", yaxis_title="Speed trap (km/h)")
        st.plotly_chart(_chart(fig, 260), use_container_width=True, config={"displayModeBar": False})
        how("Speeds are measured at fixed points on track every lap (OpenF1). Dips usually mean a tow lost, traffic, lifting to save energy, or wet running.")


def track_map(cmp, seg, ca, cb, col_a, col_b, corners):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=cmp["x"], y=cmp["y"], mode="lines", line=dict(color="#2E2E3A", width=14), hoverinfo="skip", showlegend=False))
    for who, colr in ((cb, col_b), (ca, col_a)):
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", line=dict(color=colr, width=6), name=f"{who} faster"))
    for _, r in seg.iterrows():
        part = cmp[(cmp["f"] >= r["f0"]) & (cmp["f"] <= r["f1"])]
        colr = col_b if r["gain_b"] > 0 else col_a
        fig.add_trace(go.Scatter(x=part["x"], y=part["y"], mode="lines", line=dict(color=colr, width=7), showlegend=False,
                                 hovertemplate=f"{r['where']}: {(cb if r['gain_b'] > 0 else ca)} +{abs(r['gain_b']):.3f}s<extra></extra>"))
    for num, f in duel.corner_fractions(cmp, corners):
        i = int(np.argmin(np.abs(cmp["f"] - f)))
        fig.add_annotation(x=cmp["x"].iloc[i], y=cmp["y"].iloc[i], text=str(num), showarrow=False,
                           font=dict(size=10, color="#FFFFFF"), bgcolor="rgba(21,21,30,.8)")
    fig.add_annotation(x=cmp["x"].iloc[0], y=cmp["y"].iloc[0], text="START", showarrow=True, arrowcolor="#FFFFFF",
                       font=dict(size=9, color="#FFFFFF"), ax=30, ay=-20)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    return _chart(fig, 420)


def traces_chart(cmp, ca, cb, col_a, col_b, seg):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.25, 0.25], vertical_spacing=0.04,
                        subplot_titles=("Speed (km/h)", f"Gap: {cb} ahead (+) / {ca} ahead (−), seconds", "Throttle %"))
    for tag, who, colr in (("a", ca, col_a), ("b", cb, col_b)):
        fig.add_trace(go.Scatter(x=cmp["m"], y=cmp[f"v_{tag}"], name=who, line=dict(color=colr, width=1.8),
                                 hovertemplate=f"{who} %{{y:.0f}} km/h<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=cmp["m"], y=cmp[f"thr_{tag}"], showlegend=False, line=dict(color=colr, width=1.2),
                                 hovertemplate=f"{who} %{{y:.0f}}%<extra></extra>"), row=3, col=1)
    fig.add_trace(go.Scatter(x=cmp["m"], y=-cmp["delta"], showlegend=False, line=dict(color="#FFFFFF", width=1.6),
                             hovertemplate="%{y:+.3f}s<extra></extra>"), row=2, col=1)
    fig.add_hline(y=0, line_color="#55556A", line_dash="dot", row=2, col=1)
    length = cmp["m"].iloc[-1]
    for _, r in seg.iterrows():
        fig.add_vline(x=r["f0"] * length, line_color="#2E2E3A", line_width=1)
        fig.add_annotation(x=(r["f0"] + r["f1"]) / 2 * length, y=1.0, yref="paper", text=r["where"].replace("Turn ", "T"),
                           showarrow=False, font=dict(size=9, color="#9A9AA8"))
    fig.update_xaxes(title_text="Distance from the start line (m)", row=3, col=1)
    fig.update_layout(hovermode="x unified")
    return _chart(fig, 560)


def wear_chart(wa, wb, ca, cb, col_a, col_b, la, lb):
    fig = go.Figure()
    for w, who, colr, lap in ((wa, ca, col_a, la), (wb, cb, col_b, lb)):
        if not w or w["points"].empty:
            continue
        p = w["points"]
        tyre = duel.COMPOUND_COLOUR.get(w["compound"], "#9A9AA8")
        fig.add_trace(go.Scatter(x=p["age"], y=p["time"], mode="lines+markers", name=f"{who} · {w['compound'].title()}",
                                 line=dict(color=colr, width=1.2), marker=dict(color=tyre, size=7, line=dict(color=colr, width=1.5)),
                                 customdata=p["lap"], hovertemplate=f"{who} lap %{{customdata}} · tyre %{{x}} laps old · %{{y:.3f}}s<extra></extra>"))
        if w["wear"] is not None and len(p) >= 2:
            mid_age, mid_t = p["age"].median(), p["time"].median()
            xs = [p["age"].min(), p["age"].max()]
            fig.add_trace(go.Scatter(x=xs, y=[mid_t + w["wear"] * (x - mid_age) for x in xs], mode="lines", showlegend=False,
                                     line=dict(color=colr, width=2, dash="dash"), hoverinfo="skip"))
        sel = p[p["lap"] == int(lap)]
        if len(sel):
            fig.add_trace(go.Scatter(x=sel["age"], y=sel["time"], mode="markers+text", showlegend=False, text=[f"lap {int(lap)}"],
                                     textposition="top center", textfont=dict(size=10, color="#FFFFFF"),
                                     marker=dict(symbol="star", size=16, color=colr, line=dict(color="#FFFFFF", width=1.5)), hoverinfo="skip"))
    fig.update_layout(title="Tyre wear on these stints", xaxis_title="Tyre age (laps)", yaxis_title="Lap time, fuel effect removed (s)",
                      legend=dict(orientation="h", y=1.12, x=1, xanchor="right"))
    return _chart(fig, 320)


def wear_section(raw, laps, a, b, ca, cb, col_a, col_b, la, lb):
    total = int(laps["lap_number"].max())
    try:
        wa, wb = duel.wear_on_lap(laps, raw, a, la, total), duel.wear_on_lap(laps, raw, b, lb, total)
    except Exception:
        return
    if not wa and not wb:
        return
    st.markdown("##### Tyre degradation on these laps")
    cols = st.columns(3)
    for col, w, who, colr in ((cols[0], wa, ca, col_a), (cols[1], wb, cb, col_b)):
        if not w:
            col.markdown(f"<div class='duel-card' style='border-left-color:{colr}'><div class='duel-k'>{who}</div>No tyre data.</div>", unsafe_allow_html=True)
            continue
        dot = f"<i style='display:inline-block;width:.65rem;height:.65rem;border-radius:50%;background:{duel.COMPOUND_COLOUR.get(w['compound'], '#9A9AA8')};margin-right:.3rem'></i>"
        if w["wear"] is None:
            body = "Stint too short or too disrupted to measure wear."
        elif w["wear"] < 0:
            body = (f"Laps got <b>{abs(w['wear']):.3f}s faster</b> each lap.<br>The track was improving (drying or gaining grip) faster than the tyres wore, "
                    "so wear can't be measured here.")
        else:
            body = f"Wear: <b>{w['wear']:+.3f}s per lap</b><br>Cost on this lap: <b>{w['cost']:+.2f}s</b> vs a new set"
        col.markdown(f"<div class='duel-card' style='border-left-color:{colr}'><div class='duel-k'>{who} · {dot}{w['compound'].title()} · {w['age']} laps old</div>"
                     f"<div style='font-size:.8rem;line-height:1.6'>{body}</div><div class='duel-dim' style='font-size:.68rem'>Stint: laps {w['start']} to {w['end']}</div></div>",
                     unsafe_allow_html=True)
    if wa and wb and wa["cost"] is not None and wb["cost"] is not None:
        edge = wa["cost"] - wb["cost"]
        who = cb if edge > 0 else ca
        txt = "Level" if abs(edge) < 0.02 else f"{who} +{abs(edge):.2f}s"
        cols[2].markdown(f"<div class='duel-card' style='border-left-color:#9A9AA8'><div class='duel-k'>Tyre edge on this lap</div>"
                         f"<div class='duel-v'>{txt}</div><div class='duel-dim' style='font-size:.68rem'>How much of the gap is down to tyre wear, not driving. Estimate.</div></div>",
                         unsafe_allow_html=True)
    st.plotly_chart(wear_chart(wa, wb, ca, cb, col_a, col_b, la, lb), use_container_width=True, config={"displayModeBar": False})
    how("Each dot is one lap of the stint, coloured by tyre; the star is the lap compared above. The dashed line is the wear trend: "
               "the steeper it climbs, the faster the tyres are going off. Cars get lighter as fuel burns, which hides wear, so that effect is taken out first. "
               "Cost on this lap = wear per lap × laps into the stint. Safety Car and pit laps are left out. Estimates from lap times (OpenF1).")


def telemetry_section(raw, laps, sk, a, b, ca, cb, col_a, col_b):
    st.markdown("#### One lap, corner by corner")
    common = sorted(set(laps.loc[laps["driver_number"] == a, "lap_number"]) & set(laps.loc[laps["driver_number"] == b, "lap_number"]))
    mode = st.radio("Which laps", ["Each driver's fastest lap", "Pick a lap"], horizontal=True, key=f"duel_mode_{sk}")
    timed = sorted(set(laps.loc[(laps["driver_number"] == a) & laps["lap_duration"].notna(), "lap_number"]) &
                   set(laps.loc[(laps["driver_number"] == b) & laps["lap_duration"].notna(), "lap_number"]))
    if mode == "Pick a lap" and timed:
        la = lb = st.select_slider("Lap", options=timed, value=timed[len(timed) // 2], key=f"duel_lap_{sk}")
    else:
        la, lb = _fastest(laps, a), _fastest(laps, b)
    ra, rb = (_lap_row(laps, a, la) if la else None), (_lap_row(laps, b, lb) if lb else None)
    if ra is None or rb is None or pd.isna(ra.get("lap_duration")) or pd.isna(rb.get("lap_duration")):
        st.caption("No timed lap for one of the drivers.")
        return
    try:
        ta, tb = _trace_for(sk, ra, a), _trace_for(sk, rb, b)
    except Exception:
        st.warning("Couldn't load the telemetry from OpenF1 just now. Try again in a minute.")
        return
    if ta is None or tb is None:
        st.caption("OpenF1 has no car telemetry for one of these laps.")
        return
    cmp = duel.compare(ta, tb)
    sess = raw.get("session") or {}
    corners = []
    try:
        from f1analytics.ui.pitwall_page import circuit_outline

        out = circuit_outline(sess.get("circuit_key"), sess.get("year"))
        corners = (out or {}).get("corners") or []
    except Exception:
        corners = []
    seg = duel.segment_table(cmp, corners)
    d = float(rb["lap_duration"] - ra["lap_duration"])
    faster, slower = (cb, ca) if d < 0 else (ca, cb)
    def tyre_of(r):
        comp = str(r.get("compound") or "").title()
        age = r.get("tyre_age")
        return f"{comp}, {int(age)} laps old" if comp and pd.notna(age) else (comp or "tyre unknown")

    def flags(r):
        out = []
        if bool(r.get("pit_in")):
            out.append("pit in")
        if bool(r.get("pit_out")):
            out.append("pit out")
        if bool(r.get("neutral")):
            out.append("Safety Car")
        return f" · {', '.join(out)}" if out else ""

    m = st.columns(3)
    m[0].markdown(f"<div class='duel-k'>{ca} · lap {la}</div><div class='duel-v'>{_fmt(ra['lap_duration'])}</div>"
                  f"<div class='duel-dim' style='font-size:.7rem'>{tyre_of(ra)}{flags(ra)}</div>", unsafe_allow_html=True)
    m[1].markdown(f"<div class='duel-k'>{cb} · lap {lb}</div><div class='duel-v'>{_fmt(rb['lap_duration'])}</div>"
                  f"<div class='duel-dim' style='font-size:.7rem'>{tyre_of(rb)}{flags(rb)}</div>", unsafe_allow_html=True)
    m[2].markdown(f"<div class='duel-k'>Difference</div><div class='duel-v'>{faster} {abs(d):.3f}s</div>", unsafe_allow_html=True)
    if seg.empty:
        st.caption("Couldn't split this lap into corners.")
        return
    won_b = seg[seg["gain_b"] > 0.005].sort_values("gain_b", ascending=False)
    won_a = seg[seg["gain_b"] < -0.005].sort_values("gain_b")
    c1, c2 = st.columns(2)
    for col, who, rows, colr in ((c1, cb, won_b, col_b), (c2, ca, won_a, col_a)):
        total = abs(rows["gain_b"].sum())
        items = "".join(f"<li>{html.escape(duel.explain(r, ca, cb))}</li>" for _, r in rows.head(4).iterrows())
        col.markdown(f"<div class='duel-card' style='border-left-color:{colr}'><div class='duel-k'>Where {who} was faster · {total:.3f}s in total</div>"
                     f"<ul class='duel-list'>{items or '<li>Nowhere on this lap.</li>'}</ul></div>", unsafe_allow_html=True)
    if "x" in cmp:
        st.plotly_chart(track_map(cmp, seg, ca, cb, col_a, col_b, corners), use_container_width=True, config={"displayModeBar": False})
    st.plotly_chart(traces_chart(cmp, ca, cb, col_a, col_b, seg), use_container_width=True, config={"displayModeBar": False})
    wear_section(raw, laps, a, b, ca, cb, col_a, col_b, la, lb)
    gaps = [c for c, k in ((ca, "gap_a"), (cb, "gap_b")) if seg[k].any()]
    how("both laps are placed on the track using the cars' GPS positions, then lined up so they start together. "
               "The time gap is tracked metre by metre and pinned to the official sector times, so the corners add up exactly to the real lap difference. "
               "Each corner section runs from halfway after the previous corner to halfway before the next. Telemetry: OpenF1, about 4 samples a second."
               + (f" {' and '.join(gaps)}'s data has short gaps on this lap; those corners are marked." if gaps else ""))


def duel_tab(raw, laps, sk, code, colour, present, default_a, default_b):
    st.markdown(CSS, unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    ka, kb = f"duel_a_{sk}", f"duel_b_{sk}"
    if st.session_state.get(ka) not in present:
        st.session_state[ka] = default_a
    if st.session_state.get(kb) not in present or st.session_state.get(kb) == st.session_state[ka]:
        st.session_state[kb] = default_b if default_b != st.session_state[ka] else next(n for n in present if n != st.session_state[ka])
    a = c1.selectbox("Driver", present, format_func=code.get, key=ka)
    b = c2.selectbox("Against", [n for n in present if n != a], format_func=code.get, key=kb)
    ca, cb = code.get(a, str(a)), code.get(b, str(b))
    col_a, col_b = colour.get(a, "#E10600"), colour.get(b, "#3671C6")
    if col_a.lower() == col_b.lower():
        col_b = "#9A9AA8"
    st.markdown("#### The whole race")
    gap_section(laps, a, b, ca, cb, col_a, col_b)
    tyre_section(raw, laps, a, b, ca, cb, col_a, col_b)
    telemetry_section(raw, laps, sk, a, b, ca, cb, col_a, col_b)


CSS = """<style>
.duel-head{font-size:.95rem;margin:.2rem 0 .4rem}
.duel-list{margin:.2rem 0 .4rem 1rem;padding:0;font-size:.82rem;line-height:1.55}
.duel-list li{margin:.2rem 0}
.duel-dim{opacity:.65}
.duel-t{width:100%;border-collapse:collapse;font-size:.8rem;margin:.3rem 0}
.duel-t th{text-align:left;font-size:.66rem;opacity:.7;padding:.3rem .4rem;border-bottom:1px solid var(--line)}
.duel-t td{padding:.4rem;border-bottom:1px solid var(--line);background:var(--asphalt)}
.duel-card{background:var(--asphalt);border-left:4px solid;border-radius:6px;padding:.6rem .8rem;margin:.4rem 0;min-height:100%}
.duel-k{font-size:.64rem;letter-spacing:.06em;text-transform:uppercase;opacity:.75}
.duel-v{font-size:1.25rem;margin-top:.1rem}
.ty-row{display:flex;align-items:center;gap:.6rem;margin:.3rem 0}
.ty-name{width:3rem;font-size:.8rem}
.ty-bar{flex:1;display:flex;height:26px;border-radius:4px;overflow:hidden;background:rgba(255,255,255,.05)}
.ty-seg{display:flex;align-items:center;justify-content:center;font-size:.62rem;white-space:nowrap;overflow:hidden;border-right:2px solid #15151E}
.ty-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:.4rem;vertical-align:0}
</style>"""
