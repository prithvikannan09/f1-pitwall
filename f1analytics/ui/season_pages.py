import html
import math
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from f1analytics.pitwall import season as ss

YEAR = 2026
IST = pd.Timedelta(hours=5, minutes=30)


@st.cache_data(ttl=1800, show_spinner="Loading the season…")
def load_season(year=YEAR):
    sched = ss.schedule(year)
    res = ss.results(year)
    ds, rnd = ss.driver_standings(year)
    cs, _ = ss.constructor_standings(year)
    dsp = csp = None
    if rnd and rnd > 1:
        dsp, _ = ss.driver_standings(year, rnd - 1)
        csp, _ = ss.constructor_standings(year, rnd - 1)
    return {"sched": sched, "res": res, "ds": ss.with_change(ds, dsp, "code"), "cs": ss.with_change(cs, csp, "team"), "round": rnd}


def season_or_none(year=YEAR):
    try:
        return load_season(year)
    except Exception:
        return None


def colours():
    try:
        from f1analytics.ui.pitwall_page import _grid

        return {k: v["colour"] for k, v in _grid().items()}
    except Exception:
        return {}


def team_colours(ds, by_code):
    out = {}
    for _, r in ds.iterrows():
        if r["team"] not in out and r["code"] in by_code:
            out[r["team"]] = by_code[r["code"]]
    return out


def focus_code():
    return st.session_state.get("pw_driver") or str(st.query_params.get("driver", "")).upper() or "HAM"


def _ist(ts):
    return (ts.tz_convert(None) + IST).strftime("%a %d %b, %-I:%M %p IST")


def next_session(sched, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    for r in sched:
        for name, t in r["sessions"]:
            if t is not None and t > now:
                return r, name, t
    return None, None, None


def countdown_card(r, name, t, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    secs = max(0, int((t - now).total_seconds()))
    run = f"--cd-from:{secs};--cdt:{secs};animation:cd-run {secs}s linear forwards" if secs else "--cdt:0"
    boxes = "".join(f"<div class='hc-box'><div class='hc-num {cls}' style='{run}'></div><div class='hc-unit'>{u}</div></div>"
                    for cls, u in (("hc-d", "Days"), ("hc-hr", "Hrs"), ("hc-m", "Mins"), ("hc-s", "Sec")))
    return (f"<div class='hc hc-red'><div class='hc-title'><span class='hc-tag'>R{r['round']}</span>{html.escape(r['locality'] or r['name'])}: {html.escape(name)}</div>"
            f"<div class='hc-boxes'>{boxes}</div><div class='hc-sub'>{_ist(t)}</div></div>")


def outline_svg(circuit_key, year=YEAR, w=150, h=90):
    try:
        from f1analytics.ui.pitwall_page import _rotate, circuit_outline

        out = circuit_outline(circuit_key, year)
    except Exception:
        out = None
    if not out:
        return ""
    xs, ys = _rotate(out["x"], out["y"], out.get("rotation", 0))
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    sc = min((w - 8) / max(x1 - x0, 1), (h - 8) / max(y1 - y0, 1))
    pts = " ".join(f"{4 + (x - x0) * sc:.1f},{h - 4 - (y - y0) * sc:.1f}" for x, y in zip(xs, ys))
    return (f"<svg class='hc-svg' viewBox='0 0 {w} {h}' width='{w}' height='{h}'><polyline points='{pts}' fill='none' "
            f"stroke='#FFFFFF' stroke-width='2.4' stroke-linejoin='round' stroke-linecap='round'/></svg>")


def next_gp_card(r, done, total):
    from f1analytics.pitwall.tracks import circuit_key_for

    pct = round(100 * done / total) if total else 0
    svg = outline_svg(circuit_key_for(r["locality"], r["circuit"], r["name"]))
    return (f"<div class='hc'><div class='hc-k'>{YEAR} schedule · round {r['round']} of {total}</div>"
            f"<div class='hc-row'><div><div class='hc-big'>{r['flag']} {html.escape(r['locality'] or r['name'])}</div>"
            f"<div class='hc-sub'>{html.escape(r['circuit'])}{' · Sprint weekend' if r['sprint'] else ''}</div>"
            f"<div class='hc-bar'><i style='width:{pct}%'></i></div><div class='hc-sub'>{pct}% of the season done</div></div>{svg}</div></div>")


def driver_card_html(card, colour):
    if not card:
        return "<div class='hc'><div class='hc-k'>Your driver</div><div class='hc-sub'>Pick a driver on the Live page.</div></div>"
    last = " ".join(f"<span class='hc-chip{' hc-chip-good' if str(t).isdigit() and int(t) <= 3 else ''}'>{'P' + t if str(t).isdigit() else 'DNF'}</span>"
                    for _, t in card["last5"])
    ahead = f" · {abs(card['gap_ahead']):.0f} behind {card['ahead']}" if card["ahead"] else ""
    return (f"<div class='hc' style='border-left:4px solid {colour}'><div class='hc-k'>Your driver · {html.escape(card['team'] or '')}</div>"
            f"<div class='hc-big'>P{card['pos']} {html.escape(card['driver'])}</div>"
            f"<div class='hc-sub'>{card['points']:.0f} pts · {abs(card['gap_leader']):.0f} off the lead{ahead}</div>"
            f"<div class='hc-sub'>{card['wins']} win{'' if card['wins'] == 1 else 's'} · {card['podiums']} podium{'' if card['podiums'] == 1 else 's'} · {card['dnfs']} DNF</div>"
            f"<div class='hc-k' style='margin-top:.4rem'>Last 5 races</div><div>{last}</div></div>")


def podium_card(res):
    if res.empty:
        return ""
    last = int(res["round"].max())
    lr = res[res["round"] == last].sort_values("position").head(3)
    rows = "".join(f"<div class='hc-pod'><b>P{int(r['position'])}</b> {html.escape(r['driver'])} <span class='hc-dim'>{html.escape(r['team'])}</span></div>"
                   for _, r in lr.iterrows())
    return f"<div class='hc'><div class='hc-k'>Last race · round {last}</div><div class='hc-big hc-mid'>{html.escape(lr.iloc[0]['race'])}</div>{rows}</div>"


def title_card(ds, sched, done):
    if ds.empty:
        return ""
    left = [r for r in sched if r["round"] > done]
    max_pts = sum(25 + (8 if r["sprint"] else 0) for r in left)
    lead, second = ds.iloc[0], ds.iloc[1]
    gap = lead["points"] - second["points"]
    alive = ds[ds["points"] + max_pts >= lead["points"]]
    verdict = f"{lead['driver']} has clinched the title" if len(alive) == 1 else f"{len(alive)} drivers can still win it"
    return (f"<div class='hc'><div class='hc-k'>Title fight</div><div class='hc-big hc-mid'>{html.escape(lead['family'])} leads by {gap:.0f}</div>"
            f"<div class='hc-sub'>Over {html.escape(second['family'])} with {len(left)} races and up to {max_pts} points left.</div>"
            f"<div class='hc-sub'>{verdict}.</div></div>")


def standings_table(df, key, colour_of, title, limit=10, focus=None, teams=True):
    rows = []
    for _, r in df.head(limit).iterrows():
        ch = int(r.get("change") or 0)
        evo = f"<span class='st-up'>▲{ch}</span>" if ch > 0 else (f"<span class='st-down'>▼{-ch}</span>" if ch < 0 else "<span class='hc-dim'>–</span>")
        gap = "" if r["gap"] == 0 else f"{r['gap']:.0f}"
        name = r["family"] if key == "code" else r["team"]
        sub = f"<span class='hc-dim'> {html.escape(r['team'] or '')}</span>" if key == "code" and teams else ""
        me = " st-me" if focus and r.get("code") == focus else ""
        rows.append(f"<tr class='{me}'><td>{int(r['pos'])}</td><td><i class='st-bar' style='background:{colour_of(r)}'></i>{html.escape(str(name))}{sub}</td>"
                    f"<td class='st-n'>{r['points']:.0f}</td><td class='st-gap'>{gap}</td><td>{evo}</td></tr>")
    return (f"<div class='hc hc-tab'><div class='hc-h'>{title}</div><table class='st'><tr><th>Pos</th><th>{'Driver' if key == 'code' else 'Team'}</th>"
            f"<th>Pts</th><th>Gap</th><th>Evo</th></tr>{''.join(rows)}</table></div>")


def records_card(items):
    cats = ["All", "Race", "Driver", "Team"]
    pick = st.radio("Filter", cats, horizontal=True, key="home_rec_filter", label_visibility="collapsed")
    rows = "".join(f"<div class='rec'><span class='rec-tag'>{c}</span><div><b>{html.escape(t)}</b><div class='hc-dim'>{html.escape(s)}</div></div></div>"
                   for c, t, s in items if pick == "All" or c == pick)
    st.markdown(f"<div class='hc hc-tab'>{rows or '<div class=hc-dim>Nothing here yet.</div>'}</div>", unsafe_allow_html=True)


def home():
    st.markdown(CSS, unsafe_allow_html=True)
    data = season_or_none()
    if not data:
        st.warning("Couldn't load the season from Jolpica just now. Try again in a minute.")
        return
    sched, res, ds, cs = data["sched"], data["res"], data["ds"], data["cs"]
    by_code = colours()
    tcol = team_colours(ds, by_code)
    done, total = ss.progress(sched)
    focus = focus_code()
    r, name, t = next_session(sched)
    c1, c2, c3 = st.columns(3)
    with c1:
        if r:
            st.markdown(CD_DAYS + countdown_card(r, name, t), unsafe_allow_html=True)
        else:
            st.markdown("<div class='hc'><div class='hc-big'>Season over</div></div>", unsafe_allow_html=True)
    with c2:
        nr = ss.next_race(sched)
        if nr:
            st.markdown(next_gp_card(nr, done, total), unsafe_allow_html=True)
    with c3:
        card = ss.driver_card(res, ds, focus)
        st.markdown(driver_card_html(card, by_code.get(focus, "#E10600")), unsafe_allow_html=True)
    from f1analytics.ui.extras_pages import home_cards

    up, de = home_cards()
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(podium_card(res), unsafe_allow_html=True)
    c2.markdown(title_card(ds, sched, done), unsafe_allow_html=True)
    c3.markdown(up, unsafe_allow_html=True)
    c4.markdown(de, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.markdown(standings_table(ds, "code", lambda x: by_code.get(x["code"], "#55556A"), f"{YEAR} driver standings", focus=focus, teams=False), unsafe_allow_html=True)
    c2.markdown(standings_table(cs, "team", lambda x: tcol.get(x["team"], "#55556A"), f"{YEAR} constructor standings"), unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div class='hc-h' style='margin:0 0 .3rem'>{YEAR} stats and records</div>", unsafe_allow_html=True)
        records_card(ss.records(res, ds))
    st.caption(f"Standings and results: Jolpica (Ergast), after round {data['round']}. Evo = places gained or lost since the previous round. "
               "Team colours: OpenF1.")


def standings_page():
    st.markdown(CSS, unsafe_allow_html=True)
    data = season_or_none()
    if not data:
        st.warning("Couldn't load the standings just now.")
        return
    by_code = colours()
    tcol = team_colours(data["ds"], by_code)
    c1, c2 = st.columns(2)
    c1.markdown(standings_table(data["ds"], "code", lambda x: by_code.get(x["code"], "#55556A"), f"{YEAR} drivers' championship",
                                limit=40, focus=focus_code()), unsafe_allow_html=True)
    c2.markdown(standings_table(data["cs"], "team", lambda x: tcol.get(x["team"], "#55556A"), f"{YEAR} constructors' championship", limit=20),
                unsafe_allow_html=True)
    res = data["res"]
    if not res.empty:
        import plotly.graph_objects as go

        pts = res.pivot_table(index="round", columns="code", values="points", aggfunc="sum").fillna(0).cumsum()
        top = list(data["ds"]["code"].head(8))
        fig = go.Figure()
        for code in top:
            if code in pts:
                fig.add_trace(go.Scatter(x=pts.index, y=pts[code], name=code, mode="lines",
                                         line=dict(color=by_code.get(code, "#9A9AA8"), width=3 if code == focus_code() else 1.6)))
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10), title="Points race by race (top 8, Grand Prix points only)",
                          font=dict(family="Michroma, sans-serif", color="#F3F3F5", size=11), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", xaxis_title="Round", yaxis_title="Points")
        fig.update_xaxes(gridcolor="#2E2E3A")
        fig.update_yaxes(gridcolor="#2E2E3A")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.caption("The chart adds up Grand Prix results; the tables also include Sprint points, so totals can differ slightly.")


def schedule_page():
    st.markdown(CSS, unsafe_allow_html=True)
    data = season_or_none()
    if not data:
        st.warning("Couldn't load the calendar just now.")
        return
    res = data["res"]
    now = pd.Timestamp.now(tz="UTC")
    rows = []
    for r in data["sched"]:
        won = res[(res["round"] == r["round"]) & (res["position"] == 1)]
        state = "done" if r["race_utc"] is not None and r["race_utc"] + pd.Timedelta(hours=3) <= now else "next"
        winner = f"🏆 {html.escape(won.iloc[0]['driver'])}" if len(won) else ("Up next" if state == "next" else "")
        sessions = " · ".join(f"{html.escape(n)} {(t.tz_convert(None) + IST).strftime('%a %-I:%M %p')}" for n, t in r["sessions"] if t is not None)
        rows.append(f"<div class='sch sch-{state}'><div class='sch-r'>R{r['round']}</div><div class='sch-m'><b>{r['flag']} {html.escape(r['name'])}</b>"
                    f"<div class='hc-dim'>{html.escape(r['circuit'])} · {r['race_utc'].strftime('%d %b') if r['race_utc'] is not None else ''}"
                    f"{' · Sprint' if r['sprint'] else ''}</div><div class='sch-s'>{sessions} (IST)</div></div><div class='sch-w'>{winner}</div></div>")
    st.markdown("<div class='sch-list'>" + "".join(rows) + "</div>", unsafe_allow_html=True)
    st.caption("Calendar and winners: Jolpica (Ergast). Session times shown in IST.")


def results_page():
    st.markdown(CSS, unsafe_allow_html=True)
    data = season_or_none()
    if not data or data["res"].empty:
        st.warning("Couldn't load the results just now.")
        return
    res = data["res"]
    by_code = colours()
    rounds = sorted(res["round"].unique())
    names = {r: res[res["round"] == r]["race"].iloc[0] for r in rounds}
    pick = st.selectbox("Race", rounds[::-1], format_func=lambda r: f"R{r} · {names[r]}", key="res_round")
    x = res[res["round"] == pick].sort_values("position")
    rows = "".join(
        f"<tr class='{'st-me' if r['code'] == focus_code() else ''}'><td>{r['text'] if str(r['text']).isdigit() else r['text']}</td>"
        f"<td><i class='st-bar' style='background:{by_code.get(r['code'], '#55556A')}'></i>{html.escape(r['driver'])}<span class='hc-dim'> {html.escape(r['team'])}</span></td>"
        f"<td>{r['grid'] or 'Pit'}</td><td>{(r['grid'] - r['position']) if r['grid'] else ''}</td><td class='st-n'>{r['points']:.0f}</td>"
        f"<td class='hc-dim'>{html.escape(str(r['status']))}{' · ⚡ fastest lap' if r['fastest'] else ''}</td></tr>"
        for _, r in x.iterrows())
    st.markdown(f"<div class='hc hc-tab'><table class='st'><tr><th>Pos</th><th>Driver</th><th>Grid</th><th>+/−</th><th>Pts</th><th>Status</th></tr>{rows}</table></div>",
                unsafe_allow_html=True)
    st.caption("Results: Jolpica (Ergast). +/− = places gained from the grid. For lap-by-lap detail and head to head, open Past races.")


CD_DAYS = """<style>
@property --cdt{syntax:'<integer>';initial-value:0;inherits:false}
@keyframes cd-run{from{--cdt:var(--cd-from)}to{--cdt:0}}
.hc-d{counter-reset:v calc(round(down, var(--cdt) / 86400))}
.hc-hr{counter-reset:v calc(mod(round(down, var(--cdt) / 3600), 24))}
.hc-m{counter-reset:v calc(mod(round(down, var(--cdt) / 60), 60))}
.hc-s{counter-reset:v calc(mod(var(--cdt), 60))}
.hc-num::after{content:counter(v, decimal-leading-zero)}
</style>"""

CSS = """<style>
.hc{background:var(--asphalt);border:1px solid var(--line);border-radius:10px;padding:1rem 1.1rem;margin-bottom:1rem;min-height:150px}
.hc-tab{min-height:0}
.hc-red{background:linear-gradient(135deg,#E10600,#8A0A0A);border-color:#E10600}
.hc-title{font-size:.85rem;display:flex;align-items:center;gap:.5rem}
.hc-tag{border:1px solid rgba(255,255,255,.7);border-radius:4px;padding:0 .35rem;font-size:.66rem}
.hc-boxes{display:flex;gap:1rem;margin:.8rem 0 .3rem}
.hc-num{font-size:1.9rem;line-height:1;font-variant-numeric:tabular-nums}
.hc-unit{font-size:.58rem;letter-spacing:.08em;text-transform:uppercase;opacity:.8;margin-top:.25rem}
.hc-k{font-size:.62rem;letter-spacing:.08em;text-transform:uppercase;opacity:.7;margin-bottom:.35rem}
.hc-h{font-size:1rem;margin-bottom:.5rem}
.hc-big{font-size:1.35rem;line-height:1.25;margin-bottom:.25rem}
.hc-mid{font-size:1.05rem}
.hc-sub{font-size:.72rem;opacity:.8;line-height:1.5}
.hc-dim{opacity:.6;font-size:.7rem}
.hc-row{display:flex;justify-content:space-between;align-items:center;gap:.6rem}
.hc-svg{flex:0 0 auto;opacity:.95}
.hc-bar{height:5px;border-radius:3px;background:rgba(255,255,255,.12);margin:.5rem 0 .25rem;overflow:hidden}
.hc-bar i{display:block;height:100%;background:var(--kerb)}
.hc-chip{display:inline-block;font-size:.66rem;padding:.1rem .4rem;border-radius:4px;background:rgba(255,255,255,.08);margin:.15rem .2rem 0 0}
.hc-chip-good{background:color-mix(in srgb,var(--kerb) 35%,transparent)}
.hc-pod{font-size:.78rem;padding:.25rem 0;border-top:1px solid var(--line)}
.st{width:100%;border-collapse:collapse;font-size:.74rem}
.st th{text-align:left;font-size:.58rem;letter-spacing:.06em;text-transform:uppercase;opacity:.6;padding:.35rem .3rem;border-bottom:1px solid var(--line)}
.st td{padding:.42rem .3rem;border-bottom:1px solid var(--line);white-space:nowrap}
.st tr.st-me td{background:color-mix(in srgb,var(--kerb) 14%,transparent)}
.st-n{text-align:right}
.st-gap{opacity:.6;text-align:right}
.st-bar{display:inline-block;width:3px;height:1em;vertical-align:-2px;margin-right:.45rem;border-radius:2px}
.st-up{color:#43B02A}.st-down{color:#E10600}
.rec{display:flex;gap:.6rem;align-items:flex-start;padding:.55rem 0;border-bottom:1px solid var(--line);font-size:.74rem;line-height:1.45}
.rec-tag{flex:0 0 auto;font-size:.56rem;letter-spacing:.06em;text-transform:uppercase;padding:.12rem .4rem;border-radius:4px;background:rgba(255,255,255,.08)}
.sch-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:.7rem}
.sch{display:flex;gap:.8rem;align-items:flex-start;background:var(--asphalt);border:1px solid var(--line);border-radius:10px;padding:.8rem}
.sch-done{opacity:.72}
.sch-next{border-color:var(--kerb)}
.sch-r{font-size:.7rem;opacity:.7;min-width:2rem}
.sch-m{flex:1;font-size:.8rem;line-height:1.45}
.sch-s{font-size:.62rem;opacity:.6;margin-top:.3rem}
.sch-w{font-size:.72rem;text-align:right;max-width:9rem}
</style>"""
