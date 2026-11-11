import html
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from f1analytics.pitwall import pu_elements as pu
from f1analytics.ui import extras_pages
from f1analytics.ui.duel_panel import CSS as DUEL_CSS
from f1analytics.ui.duel_panel import _chart
from f1analytics.ui.season_pages import CSS, focus_code

PU_RULES = """
**How engine parts work (2026 rules)**
- The power unit is split into parts: the engine itself (ICE), turbo, exhaust, the MGU-K (the electric motor that recovers and deploys energy at the rear axle), the battery (energy store), the control electronics and smaller ancillary parts.
- Each driver gets a fixed number of each part for the season: 4 engines, 4 turbos, 4 exhausts, 3 MGU-Ks, 3 batteries and 3 control electronics units.
- Fitting one more than allowed is a grid penalty, even if the new part is no faster: 10 places for the first part over the limit, 5 for each one after. A penalty bigger than 15 places means starting from the back. Fitting a whole new power unit at once is the usual "back of the grid" case.
- Teams sometimes take a penalty on purpose at a track where overtaking is easy, so the driver has fresh parts for the rest of the season.
- Engine parts are not "upgrades": the power unit design is frozen during the season. The aero parts in the other tab are where teams find speed.
"""


def code_of(name):
    import unicodedata

    last = str(name).split()[-1]
    return unicodedata.normalize("NFKD", last).encode("ascii", "ignore").decode()[:3].upper()


def _grid():
    return extras_pages._grid()


def team_colours():
    from f1analytics.pitwall.season_form import team_name

    out = {}
    for v in _grid().values():
        if v.get("team"):
            out[team_name(v["team"])] = v["colour"]
            out[v["team"]] = v["colour"]
    return out


def _colour_for(team, cols):
    t = str(team).lower()
    for k, c in cols.items():
        kk = k.lower()
        if t.startswith(kk.split()[0]) and not (kk.startswith("red bull") and "racing bulls" in t) and not (kk.startswith("racing bulls") and t.startswith("red bull")):
            return c
    return "#9A9AA8"


def _after_doc_notes(ev):
    try:
        from f1analytics.ui.buildup_panel import weekend_notes

        notes = weekend_notes()
    except Exception:
        return []
    if not notes or not ev or str(notes.get("meeting", "")).lower() not in str(ev.get("label", "")).lower():
        return []
    return [p for p in notes.get("penalties", []) if any(w in str(p.get("reason", "")).lower() for w in ("engine", "power unit", "turbo", "exhaust", "ice"))]


def engine_tab():
    data = pu.load()
    if not data or not data.get("events"):
        st.caption("Engine component data isn't available.")
        return
    try:
        aduo_section()
    except Exception:
        import logging

        logging.getLogger("f1analytics").exception("aduo failed")
    st.markdown("#### Engine parts used by every driver")
    labels = [e["label"] for e in data["events"]]
    i = st.selectbox("As of", list(range(len(labels)))[::-1], format_func=lambda k: labels[k], key="up_pu_event")
    ev, df = pu.table(data, i)
    cols = team_colours()
    focus = focus_code()
    st.markdown(f"<div class='hc hc-tab' style='min-height:0'><div class='hc-k'>Engine parts used this season · official FIA count</div>"
                f"<div class='hc-big hc-mid'>{html.escape(ev['label'])} · {html.escape(str(ev['date']))}, {html.escape(str(ev['time']))} local time</div>"
                f"<div class='hc-sub'>Published on the Friday morning, before practice. Parts fitted later that weekend show up at the next race.</div></div>",
                unsafe_allow_html=True)
    head = "".join(f"<th>{html.escape(pu.NAMES[e])}<br><span class='duel-dim'>{'limit ' + str(pu.LIMITS[e]) if e in pu.LIMITS else 'no limit published'}</span></th>"
                   for e in pu.ELEMENTS)
    body = ""
    for _, r in df.iterrows():
        cells = ""
        for e in pu.ELEMENTS:
            v, lim = int(r[e]), pu.LIMITS.get(e)
            style = ""
            if lim and v > lim:
                style = " style='background:rgba(225,6,0,.35);font-weight:bold'"
            elif lim and v == lim:
                style = " style='background:rgba(255,209,46,.18)'"
            cells += f"<td{style}>{v}</td>"
        me = " style='outline:1px solid #E10600'" if focus and code_of(r["driver"]) == focus else ""
        body += (f"<tr{me}><td><i class='ty-dot' style='background:{_colour_for(r['team'], cols)}'></i>{html.escape(r['driver'])}"
                 f"<div class='duel-dim' style='font-size:.62rem'>{html.escape(r['team'])}</div></td>{cells}</tr>")
    st.markdown(f"<div style='overflow-x:auto'><table class='duel-t'><tr><th>Driver</th>{head}</tr>{body}</table></div>", unsafe_allow_html=True)
    st.caption("Red = over the season limit (each one over brought a grid penalty when it was fitted). Yellow = at the limit: the next one is a penalty.")
    over = pu.over_limit(df)
    if over:
        items = "".join(f"<li><b>{html.escape(d)}</b>: " + ", ".join(f"{pu.NAMES[e].lower()} +{n}" for e, n in x.items()) + "</li>"
                        for d, x in sorted(over.items(), key=lambda kv: -sum(kv[1].values())))
        st.markdown(f"<div class='duel-card' style='border-left-color:#E10600'><div class='duel-k'>Over the limit</div><ul class='duel-list'>{items}</ul></div>",
                    unsafe_allow_html=True)
    ch = pu.changes(data, i)
    if len(ch):
        prev = labels[i - 1]
        items = "".join(f"<li><b>{html.escape(r['driver'])}</b> <span class='duel-dim'>{html.escape(r['team'])}</span>: "
                        + ", ".join(f"{n} new {pu.NAMES[e].lower()}" if n > 1 else f"new {pu.NAMES[e].lower()}" for e, n in r["new"].items()) + "</li>"
                        for _, r in ch.iterrows())
        st.markdown(f"<div class='duel-card' style='border-left-color:#FFD12E'><div class='duel-k'>Fitted between {html.escape(prev)} and {html.escape(ev['label'])} (Friday to Friday)</div>"
                    f"<ul class='duel-list'>{items}</ul></div>", unsafe_allow_html=True)
    late = _after_doc_notes(ev)
    if late:
        items = "".join(f"<li><b>{html.escape(p['code'])}</b>: {html.escape(p['drop'])} · {html.escape(p['reason'])}</li>" for p in late)
        st.markdown(f"<div class='duel-card' style='border-left-color:#9A9AA8'><div class='duel-k'>Fitted after this count, during the {html.escape(ev['label'])} weekend</div>"
                    f"<ul class='duel-list'>{items}</ul></div>", unsafe_allow_html=True)
    team_totals(df, cols)
    driver_chart(data, df)
    with st.expander("How engine parts and penalties work"):
        st.markdown(PU_RULES)
    st.caption(f"Source: [FIA Technical Delegate's Report, {ev['label']}]({ev['url']}). Limits and penalty rules: "
               "[Formula1.com guide to power unit penalties](https://www.formula1.com/en/latest/article/the-beginners-guide-to-formula-1-engine-and-gearbox-penalties.2TSy7BFgEvdNLojGLWS3F1). "
               "The Bahrain GP at Sepang count isn't in the FIA archive under the usual name, so that race is skipped.")


def team_totals(df, cols):
    lim = [e for e in pu.LIMITS]
    t = df.assign(total=df[lim].sum(axis=1)).groupby("team")["total"].sum().sort_values()
    base = sum(pu.LIMITS.values()) * 2
    fig = go.Figure(go.Bar(x=t.values, y=t.index, orientation="h", marker_color=[_colour_for(x, cols) for x in t.index],
                           text=[f"{int(v)}" for v in t.values], textposition="outside", hovertemplate="%{y}: %{x} parts<extra></extra>"))
    fig.add_vline(x=base, line_color="#E10600", line_dash="dot", annotation_text="season allowance for 2 cars", annotation_font_size=9)
    fig.update_layout(title="Engine parts used per team (both cars, excluding ancillaries)", xaxis_title="Parts", showlegend=False)
    st.plotly_chart(_chart(fig, 60 + 30 * len(t)), use_container_width=True, config={"displayModeBar": False})
    st.caption("A rough reliability guide: more parts usually means more failures or more strategic penalties. Note teams supplied by the same engine maker share the same design.")


def driver_chart(data, df):
    drivers = list(df["driver"])
    focus = focus_code()
    default = next((d for d in drivers if focus and code_of(d) == focus), None)
    if default is None:
        default = next((d for d in drivers if "Hamilton" in d), drivers[0])
    who = st.multiselect("Compare drivers", drivers, default=[default], key="up_pu_drivers", max_selections=4)
    el = st.radio("Part", [e for e in pu.ELEMENTS if e in pu.LIMITS], format_func=lambda e: pu.NAMES[e], horizontal=True, key="up_pu_el")
    fig = go.Figure()
    for d in who:
        h = pu.history(data, d)
        if len(h):
            fig.add_trace(go.Scatter(x=h["event"], y=h[el], mode="lines+markers", name=d, line_shape="hv",
                                     hovertemplate=f"{d} · %{{x}}: %{{y}} used<extra></extra>"))
    fig.add_hline(y=pu.LIMITS[el], line_color="#E10600", line_dash="dot", annotation_text="season limit", annotation_font_size=9)
    fig.update_layout(title=f"{pu.NAMES[el]}: used through the season", yaxis_title="Used so far", xaxis_tickangle=-45)
    st.plotly_chart(_chart(fig, 340), use_container_width=True, config={"displayModeBar": False})


def page():
    from f1analytics.ui import performance_page as pp

    st.markdown(CSS + DUEL_CSS, unsafe_allow_html=True)
    st.subheader("Upgrades")
    t1, t2, t3 = st.tabs(["Car parts", "Engine components", "Did the upgrades work?"])
    with t1:
        extras_pages.upgrades_page()
        d = extras_pages.load()
        pp.latest_section(d, _grid(), None)
        pp.all_section(d, _grid(), None)
    with t2:
        try:
            engine_tab()
        except Exception:
            import logging

            logging.getLogger("f1analytics").exception("engine tab failed")
            st.warning("The engine components view hit a snag.")
    with t3:
        try:
            cols = team_colours()
            from f1analytics.pitwall.season_form import team_name

            mine = next((v.get("team") for c, v in _grid().items() if c == focus_code()), None)
            pp.season_upgrades_tab(cols, [team_name(mine)] if mine else [])
        except Exception:
            import logging

            logging.getLogger("f1analytics").exception("season upgrades failed")
            st.warning("The season view hit a snag.")


MAKER_COLOUR = {"Red Bull Ford": "#3671C6", "Mercedes": "#27F4D2", "Ferrari": "#E80020", "Honda": "#229971", "Audi": "#BB0A30"}
BAND_TONE = {"Benchmark": "#43B02A", "2-4% behind": "#FFD12E", "More than 4% behind": "#E10600"}


def aduo_tables(data, a):
    from f1analytics.pitwall import season_form as sf

    sp = sf.maker_speed(data, a)
    per = sp.groupby(["period", "maker"])[["top_speed_kmh", "clip_kmh"]].mean().reset_index() if len(sp) else pd.DataFrame()
    bench = "Red Bull Ford"
    if len(per):
        b = per[per["maker"] == bench].set_index("period")
        per["gap_top"] = per["top_speed_kmh"] - per["period"].map(b["top_speed_kmh"])
        per["gap_clip"] = per["clip_kmh"] - per["period"].map(b["clip_kmh"])
    return per


def aduo_section(focus_teams=(), compact=False):
    from f1analytics.pitwall import season_form as sf
    from f1analytics.pitwall.racecraft import load as rc_load

    a = sf.aduo()
    if not a:
        return
    data = rc_load() or {}
    per = aduo_tables(data, a)
    st.markdown("#### Engine benchmark (FIA ICE ranking) for the whole grid")
    periods = a["periods"]
    head = "".join(f"<th>{html.escape(p['name'])}<br><span class='duel-dim'>{html.escape(p['races'])}</span></th>" for p in periods)
    rows = ""
    for maker, teams in a["makers"].items():
        cells = ""
        for p in periods:
            band = p["bands"].get(maker)
            g = p["granted"].get(maker)
            if band:
                cells += f"<td style='color:{BAND_TONE.get(band, '#F3F3F5')}'>{html.escape(band)}<div class='duel-dim' style='font-size:.62rem'>upgrades granted: {html.escape(str(g))}</div></td>"
            else:
                cells += f"<td class='duel-dim'>not published<div style='font-size:.62rem'>upgrades granted: {html.escape(str(g))}</div></td>"
        trend = ""
        if len(per):
            x = per[per["maker"] == maker].sort_values("period")
            if maker == "Red Bull Ford":
                trend = "benchmark"
            elif len(x) >= 2:
                first, last = x["gap_top"].iloc[0], x["gap_top"].iloc[-1]
                ch = last - first
                word = "catching up" if ch >= 1 else ("falling back" if ch <= -1 else "holding")
                tone = "#43B02A" if word == "catching up" else ("#E10600" if word == "falling back" else "#9A9AA8")
                trend = (f"<span style='color:{tone}'><b>{word}</b></span><div class='duel-dim' style='font-size:.62rem'>top speed vs Red Bull Ford: "
                         + " → ".join(f"{v:+.1f}" for v in x["gap_top"]) + " km/h</div>")
        mine = any(t in focus_teams for t in teams)
        ring = " style='outline:1px solid #F3F3F5'" if mine else ""
        rows += (f"<tr{ring}><td><i class='ty-dot' style='background:{MAKER_COLOUR.get(maker, '#9A9AA8')}'></i><b>{html.escape(maker)}</b>"
                 f"<div class='duel-dim' style='font-size:.62rem'>{html.escape(', '.join(teams))}</div></td>{cells}<td>{trend}</td></tr>")
    st.markdown(f"<div style='overflow-x:auto'><table class='duel-t'><tr><th>Engine (teams using it)</th>{head}<th>Our telemetry: straight-line trend</th></tr>{rows}</table></div>",
                unsafe_allow_html=True)
    notes = " ".join(f"{p['name']}: {p['note']}" for p in periods if p.get("note"))
    st.caption(f"{a['what']} {notes} {a['next']}")
    if compact or not len(per):
        if compact:
            st.caption("Full engine benchmark chart and engine part counts: 🔧 Upgrades → Engine components.")
        return
    metric = st.radio("Telemetry", ["Top speed vs Red Bull Ford", "Speed lost before braking (energy running out)"], horizontal=True, key="up_aduo_metric")
    col = "gap_top" if metric.startswith("Top") else "gap_clip"
    fig = go.Figure()
    names = [f"{p['name']}\n{p['races']}" for p in periods] + ["Since Austin"]
    for maker in a["makers"]:
        x = per[per["maker"] == maker].sort_values("period")
        fig.add_trace(go.Scatter(x=[names[int(k)] for k in x["period"]], y=x[col], name=maker, mode="lines+markers",
                                 line=dict(color=MAKER_COLOUR.get(maker), width=2.6), hovertemplate=f"{maker} · %{{x}}: %{{y:+.1f}} km/h<extra></extra>"))
    fig.add_hline(y=0, line_color="#55556A", line_dash="dot")
    fig.update_layout(title="Straight-line telemetry by engine maker, compared with the benchmark (Red Bull Ford)", yaxis_title="km/h")
    if col == "gap_clip":
        fig.update_yaxes(autorange="reversed")
    st.plotly_chart(_chart(fig, 340), use_container_width=True, config={"displayModeBar": False})
    st.caption("Our own estimate, not the FIA's: average of every car using that engine, from OpenF1 telemetry on each straight compared with the field median. "
               "Top speed also depends on how much wing a team runs and on the battery, so treat it as a clue, not an engine measurement. "
               "Speed lost before braking shows cars running out of electric energy at the end of straights; less is better (chart flipped so up is better). "
               "Sources: " + " · ".join(f"[{t}]({u})" for t, u in a["sources"]))
