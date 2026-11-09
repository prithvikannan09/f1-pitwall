import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from f1analytics.pitwall import review as rv
from f1analytics.ui import glossary as gl

TYRE_COLOUR = {"SOFT": "#DA291C", "MEDIUM": "#FFD12E", "HARD": "#F0F0EC", "INTERMEDIATE": "#43B02A", "WET": "#0067AD"}
FONT = dict(family="Michroma, sans-serif", color="#F3F3F5")

CSS = """
<style>
.rv-line{background:var(--asphalt);border-radius:5px;padding:.5rem .8rem;margin:.3rem 0;font-size:.92rem;border-left:3px solid var(--kerb)}
.rv-line.good{border-left-color:#00B050}
.rv-moment{font-size:.86rem;color:var(--tarmac);margin:.15rem 0}
.rv-moment b{color:#F3F3F5}
</style>
"""


@st.cache_data(ttl=6 * 3600, show_spinner="Loading the race review from OpenF1…", max_entries=8)
def fetch(session_key):
    from f1analytics.sources.openf1_source import OpenF1Source, _ts

    src = OpenF1Source(timeout=20, retries=3)
    sk = int(session_key)
    raw = {ep: src._get(ep, session_key=sk) for ep in ("drivers", "laps", "stints", "pit", "race_control", "position", "session_result")}
    sess = src._get("sessions", session_key=sk)
    raw["weekend_stints"], raw["sprint"] = pd.DataFrame(), False
    if not sess.empty:
        allsess = src._get("sessions", meeting_key=int(sess["meeting_key"].iloc[0]))
        start = _ts(sess["date_start"]).iloc[0]
        allsess = allsess[_ts(allsess["date_start"]) <= start]
        raw["sprint"] = bool(allsess["session_name"].astype(str).str.contains("Sprint").any())
        parts = []
        for k in allsess["session_key"]:
            s = src._get("stints", session_key=int(k))
            if not s.empty:
                parts.append(s.assign(session_key=int(k)))
        raw["weekend_stints"] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return raw


def load(rep):
    raw = getattr(rep, "raw", None) or {}
    sk = (raw.get("session") or {}).get("session_key")
    if sk and os.environ.get("F1_REVIEW_FETCH", "1") != "0":
        try:
            got = fetch(int(sk))
            if not got["laps"].empty:
                return got, int(sk)
        except Exception:
            pass
    return dict(raw), sk


def lap_fmt(s):
    if s is None or pd.isna(s):
        return "–"
    m, sec = divmod(float(s), 60)
    return f"{int(m)}:{sec:06.3f}"


def gap_fmt(g, focus_code):
    if g is None or pd.isna(g):
        return "–"
    return f"{g:+.3f} s" + (" (faster)" if g < 0 else "")


def _chart(fig, height=320):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), font=FONT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), hovermode="x unified")
    fig.update_xaxes(gridcolor="#2E2E3A")
    fig.update_yaxes(gridcolor="#2E2E3A")
    return fig


def _shade_neutral(fig, laps):
    n = sorted(set(laps.loc[laps["neutral"], "lap_number"]))
    for a in n:
        fig.add_vrect(x0=a - 0.5, x1=a + 0.5, fillcolor="#FFD12E", opacity=0.10, line_width=0, layer="below")


def pace_tab(laps, focus, nums, code, colour):
    table = rv.pace_by_phase(laps, focus, nums[1:])
    if table.empty:
        st.caption("Not enough clean laps to compare pace.")
        return
    gl.plain("Each phase is a stretch of green-flag racing. Times are medians of clean laps. The gap is how much slower (+) or faster (−) "
             f"each driver was than {code[focus]} per lap, and the tyre column says what they were on for most of that phase.")
    lines = []
    for (label, a, b), g in table.groupby(["phase", "start", "end"], sort=False):
        mine = g[g["driver_number"] == focus].iloc[0]
        rows = []
        for _, r in g.iterrows():
            rows.append({"Driver": code.get(r["driver_number"], r["driver_number"]), "Tyres": r["tyre"], "Median lap": lap_fmt(r["median"]),
                         f"vs {code[focus]}": "–" if r["driver_number"] == focus else gap_fmt(r["gap"], code[focus]),
                         "Best": lap_fmt(r["best"]), "Wear s/lap": "–" if pd.isna(r["deg"]) else f"{r['deg']:+.3f}",
                         "Clean laps": int(r["laps"]), "Tyre edge": r["edge"] or "–"})
        st.markdown(f"**{label}**")
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        for _, r in g[g["driver_number"] != focus].iterrows():
            if pd.notna(r["gap"]) and pd.notna(mine["median"]):
                who = code.get(r["driver_number"])
                verdict = f"{code[focus]} {abs(r['gap']):.3f} s/lap {'quicker' if r['gap'] > 0 else 'slower'} than {who}"
                lines.append((r["gap"] > 0, f"{label}: {verdict}" + (f" · {r['edge']}" if r["edge"] and r["edge"] != "even" else "")))
    with st.expander("In plain words", expanded=True):
        for good, txt in lines:
            st.markdown(f"<div class='rv-line{' good' if good else ''}'>{txt}</div>", unsafe_allow_html=True)
    fig = go.Figure()
    for n in nums:
        x = laps[(laps["driver_number"] == n) & laps["clean"]]
        fig.add_trace(go.Scatter(x=x["lap_number"], y=x["lap_duration"], mode="lines+markers", name=code.get(n, str(n)),
                                 line=dict(color=colour.get(n, "#888"), width=3 if n == focus else 1.5), marker=dict(size=5 if n == focus else 3),
                                 customdata=[[c or "?", int(a) if pd.notna(a) else 0] for c, a in zip(x["compound"], x["tyre_age"])],
                                 hovertemplate="%{y:.3f}s · %{customdata[0]} %{customdata[1]} laps<extra>" + code.get(n, "") + "</extra>"))
    _shade_neutral(fig, laps)
    fig.update_yaxes(title_text="Clean lap (s)")
    fig.update_xaxes(title_text="Lap")
    st.plotly_chart(_chart(fig), key="rv_pace_chart", config={"displayModeBar": False})


def strategy_tab(raw, laps, focus, nums, code):
    fig = go.Figure()
    for n in reversed(nums):
        for s in rv.strategy(laps, n):
            state = "new" if s["new"] else f"used, {s['age_start']} laps old"
            fig.add_trace(go.Bar(y=[code.get(n, str(n))], x=[s["end"] - s["start"] + 1], base=[s["start"] - 0.5], orientation="h",
                                 marker=dict(color=TYRE_COLOUR.get(s["compound"], "#888"), opacity=1.0 if s["new"] else 0.5,
                                             line=dict(color="#15151E", width=2)),
                                 text=f"{s['short']}{'' if s['new'] else ' used'}", textposition="inside", insidetextanchor="middle", textangle=0,
                                 textfont=dict(color="#15151E"), showlegend=False,
                                 hovertemplate=f"{s['compound'].title()} · {state} · laps {s['start']}–{s['end']}<extra></extra>"))
    _shade_neutral(fig, laps)
    fig.update_layout(barmode="overlay", bargap=0.35)
    fig.update_xaxes(title_text="Lap")
    st.plotly_chart(_chart(fig, 70 + 42 * len(nums)), key="rv_strategy", config={"displayModeBar": False})
    st.caption("Bright bar: new set. Faded bar: used set. Yellow shading: Safety Car or red flag.")
    rows, notes = [], []
    ends = rv.race_time(laps)
    for n in nums:
        for s in rv.stops(raw, laps, n):
            rows.append({"Driver": code.get(n, str(n)), "Lap": s["lap"], "When": s["condition"],
                         "Pit-lane time": "–" if s["pit_lane"] is None else f"{s['pit_lane']:.1f} s",
                         "vs normal stop": "–" if s["extra"] is None else f"{s['extra']:+.1f} s",
                         "Penalty served": f"{s['penalty']} s" if s["penalty"] else "–", "Tyres off → on": f"{s['from']} → {s['to']}"})
            if n == focus and s["extra"] is not None and s["extra"] > 0.5:
                parts = ([f"{s['penalty']} s penalty"] if s["penalty"] else []) + ([f"{s['slow']:.1f} s slower stop"] if s["slow"] and s["slow"] > 0.3 else [])
                lost = rv.stop_cost(laps, n, s, ends)
                msg = f"Lap {s['lap']} stop cost {s['extra']:.1f} s more than a normal stop" + (f" ({' + '.join(parts)})" if parts else "")
                if lost:
                    names = ", ".join(f"{code.get(d, d)} (would have been ~{s['extra'] - g:.1f} s ahead)" for d, g in lost)
                    msg += f". Without it, {code[focus]} would likely have rejoined ahead of {names}. Estimate, assuming nothing else changed."
                else:
                    msg += ". It didn't cost a place at the rejoin."
                notes.append(msg)
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.caption("No pit stops recorded.")
    for m in notes:
        st.markdown(f"<div class='rv-line'>{m}</div>", unsafe_allow_html=True)
    gl.plain("A normal stop here is the median pit-lane time of every green-flag stop in this race. Stops under a red flag are free tyre changes, so they show no time.")


def sectors_tab(laps, focus, nums, code):
    wins = rv.phases(laps, focus)
    opts = ["Whole race"] + [f"Laps {a}–{b}" for a, b in wins]
    pick = st.radio("Which laps", opts, horizontal=True, key=f"rv_sec_win_{focus}", index=len(opts) - 1)
    win = None if pick == "Whole race" else wins[opts.index(pick) - 1]
    sec = rv.sectors(laps, nums, win)
    if sec.empty:
        st.caption("No sector data for these laps.")
        return
    names = {"duration_sector_1": "Sector 1", "duration_sector_2": "Sector 2", "duration_sector_3": "Sector 3",
             "i1_speed": "Speed check 1", "i2_speed": "Speed check 2", "st_speed": "Speed trap"}
    out = sec.rename(columns=names)
    out.index = [code.get(n, str(n)) for n in out.index]
    fmt = {c: ("{:.3f}" if c.startswith("Sector") else "{:.0f} km/h") for c in out.columns}
    best = {c: (out[c].min() if c.startswith("Sector") else out[c].max()) for c in out.columns}

    def hi(col):
        return ["background-color: rgba(0,176,80,.28); font-weight:700" if v == best[col.name] else "" for v in col]

    st.dataframe(out.style.format(fmt).apply(hi), use_container_width=True)
    me = sec.loc[focus] if focus in sec.index else None
    if me is not None:
        for n in sec.index:
            if n == focus:
                continue
            d = [(names[c], me[c] - sec.loc[n][c]) for c in ("duration_sector_1", "duration_sector_2", "duration_sector_3") if c in sec]
            if d:
                worst = max(d, key=lambda x: x[1])
                bestd = min(d, key=lambda x: x[1])
                st.markdown(f"<div class='rv-line'>vs {code.get(n)}: {code[focus]} loses most in {worst[0]} ({worst[1]:+.3f} s), "
                            f"gains most in {bestd[0]} ({bestd[1]:+.3f} s).</div>", unsafe_allow_html=True)
    gl.plain("Medians over clean laps. Green marks the best in each column. Speed checks are fixed points on the lap; the speed trap is the fastest point, usually the end of the main straight.")


def positions_tab(raw, laps, focus, nums, code, colour):
    pos = rv.positions(raw, laps)
    if pos.empty:
        st.caption("Position data isn't available for this replay.")
        return
    fig = go.Figure()
    for n in nums:
        if n not in pos:
            continue
        y = pos[n].dropna()
        fig.add_trace(go.Scatter(x=y.index, y=y.values, mode="lines", name=code.get(n, str(n)), line=dict(color=colour.get(n, "#888"), width=3.5 if n == focus else 1.8, shape="hv")))
        pits = [s["lap"] for s in rv.stops(raw, laps, n)]
        py = [pos[n].get(l) for l in pits]
        fig.add_trace(go.Scatter(x=pits, y=py, mode="markers", marker=dict(symbol="triangle-down", size=10, color=colour.get(n, "#888"), line=dict(color="#fff", width=1)),
                                 name=f"{code.get(n)} stop", showlegend=False, hovertemplate="Pit stop lap %{x}<extra>" + code.get(n, "") + "</extra>"))
    _shade_neutral(fig, laps)
    fig.update_yaxes(autorange="reversed", title_text="Position", dtick=1)
    fig.update_xaxes(title_text="Lap")
    st.plotly_chart(_chart(fig, 360), key="rv_positions", config={"displayModeBar": False})
    st.caption("Triangles mark pit stops. Yellow shading: Safety Car or red flag.")


def sets_tab(raw, sk, nums, code):
    sets = rv.weekend_sets(raw.get("weekend_stints"), sk, bool(raw.get("sprint"))) if sk else pd.DataFrame()
    if sets.empty:
        st.caption("Tyre sets need the whole weekend's data from OpenF1, which isn't available for this replay.")
        return
    alloc = rv.ALLOCATION["sprint" if raw.get("sprint") else "standard"]
    rows = []
    for n in nums:
        if n not in sets.index:
            continue
        r = sets.loc[n]
        row = {"Driver": code.get(n, str(n))}
        for c in rv.DRY:
            row[f"New {c.title()} left at start"] = f"{int(r[f'{c}_left'])} of {alloc[c]}"
            row[f"{c.title()} new in race"] = int(r[f"{c}_race"])
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    gl.plain(f"Counted from every new set fitted in {'practice, the sprint and qualifying' if raw.get('sprint') else 'practice and qualifying'}. Estimate: it assumes the usual allocation of "
             f"{alloc['SOFT']} soft, {alloc['MEDIUM']} medium and {alloc['HARD']} hard sets, and some sets are handed back to Pirelli after practice, so a set can count as used even if a team never would have raced it.")


def moments_list(raw, focus, code):
    items = rv.moments(raw, focus)
    if not items:
        return
    with st.expander(f"Key moments for {code[focus]} from race control"):
        for m in items:
            lap = f"Lap {m['lap']}" if m["lap"] else ""
            txt = m["message"].capitalize() if not m["mine"] else f"<b>{m['message'].capitalize()}</b>"
            st.markdown(f"<div class='rv-moment'>{lap} · {txt}</div>", unsafe_allow_html=True)


def review_section(rep, focus_code=None):
    if rep is None or not hasattr(rep, "total_laps"):
        return
    st.markdown(CSS, unsafe_allow_html=True)
    st.subheader("Race review")
    raw, sk = load(rep)
    if not raw.get("session"):
        raw = dict(raw, session=(getattr(rep, "raw", None) or {}).get("session") or {})
    laps = rv.lap_table(raw)
    if laps.empty:
        st.caption("No lap data for this race yet.")
        return
    code = rv.codes(raw)
    colour = rv.colours(raw)
    by_code = {v: k for k, v in code.items()}
    present = sorted(set(laps["driver_number"]) & set(code), key=lambda n: code[n])
    if not present:
        return
    fkey = f"rv_focus_{sk}"
    if st.session_state.get("rv_follow") != focus_code:
        st.session_state["rv_follow"] = focus_code
        st.session_state.pop(fkey, None)
    if st.session_state.get(fkey) not in present:
        st.session_state[fkey] = by_code.get(focus_code, present[0])
    c1, c2 = st.columns([1, 3])
    focus = c1.selectbox("Driver", present, format_func=code.get, key=fkey)
    rkey = f"rv_rivals_{sk}_{focus}"
    if rkey not in st.session_state:
        st.session_state[rkey] = [r for r in rv.default_rivals(raw, laps, focus) if r in present]
    rivals = c2.multiselect("Compare with", [n for n in present if n != focus], format_func=code.get, key=rkey, max_selections=5)
    nums = [focus] + [r for r in rivals if r != focus]
    for n in nums:
        if colour.get(n, "").lower() == colour.get(focus, "").lower() and n != focus:
            colour = {**colour, n: "#9A9AA8"}
    t0, t1, t2, t3, t4, t5 = st.tabs(["Head to head", "Pace & tyres", "Pit strategy", "Track sectors", "Positions", "Tyre sets"])
    with t0:
        from f1analytics.ui.duel_panel import duel_tab

        others = [n for n in present if n != focus]
        default_b = nums[1] if len(nums) > 1 else (others[0] if others else focus)
        try:
            duel_tab(raw, laps, sk, code, colour, present, focus, default_b)
        except Exception:
            import logging

            logging.getLogger("f1analytics").exception("head to head failed")
            st.warning("The head-to-head view hit a snag for this race. The other tabs still work.")
    with t1:
        pace_tab(laps, focus, nums, code, colour)
    with t2:
        strategy_tab(raw, laps, focus, nums, code)
    with t3:
        sectors_tab(laps, focus, nums, code)
    with t4:
        positions_tab(raw, laps, focus, nums, code, colour)
    with t5:
        sets_tab(raw, sk, nums, code)
    moments_list(raw, focus, code)
    gl.words("review", "Race review words explained")
