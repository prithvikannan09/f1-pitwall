import html
import os
import unicodedata

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from f1analytics.pitwall import duel, whatif
from f1analytics.pitwall import review as rv
from f1analytics.pitwall import strategy_sim as sim
from f1analytics.ui import extras_pages
from f1analytics.ui.duel_panel import CSS as DUEL_CSS
from f1analytics.ui.duel_panel import _chart
from f1analytics.ui.season_pages import CSS, focus_code

YEAR = 2026
COND_COLOUR = {"dry": "rgba(160,160,175,.10)", "inter": "rgba(67,176,42,.22)", "wet": "rgba(0,103,173,.28)"}
ALIASES = {"kuala lumpur": "sepang", "marina bay": "singapore", "miami gardens": "miami", "monte carlo": "monaco"}


def _plain(s):
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def races(year=YEAR):
    from f1analytics.sources.openf1_source import OpenF1Source

    s = OpenF1Source(timeout=20, retries=2)._get("sessions", year=int(year), session_name="Race")
    if s.empty:
        return []
    s = s[pd.to_datetime(s["date_start"], utc=True) < pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=3)]
    return [{"key": int(r["session_key"]), "name": f"{r['location']} ({r['country_name']})", "location": r["location"],
             "circuit": r["circuit_short_name"], "round": i + 1} for i, (_, r) in enumerate(s.sort_values("date_start").iterrows())]


@st.cache_data(ttl=6 * 3600, show_spinner="Loading the weather from OpenF1…", max_entries=8)
def weather(session_key):
    from f1analytics.sources.openf1_source import OpenF1Source

    return OpenF1Source(timeout=20, retries=2)._get("weather", session_key=int(session_key))


@st.cache_data(ttl=6 * 3600, show_spinner="Working out the tyre model for this race…", max_entries=8)
def model_for(session_key):
    from f1analytics.ui.review_panel import fetch

    raw = fetch(int(session_key))
    laps = rv.lap_table(raw)
    try:
        rain = sim.rain_by_lap(weather(int(session_key)), laps)
    except Exception:
        rain = None
    m = sim.fit(raw, laps, rain)
    return m, sim.best_by_start(m), sim.optimise(m)[:8]


def round_for(race, rounds):
    names = [_plain(race.get("location")), _plain(race.get("circuit"))]
    names += [ALIASES[n] for n in names if n in ALIASES]
    for r in rounds:
        lab = _plain(r["label"])
        if any(n and n in lab for n in names):
            return r
    return None


def upgrades_section(race, raw, model, focus=()):
    d = extras_pages.load()
    grid = extras_pages._grid()
    r = round_for(race, d["upgrades"]["rounds"])
    st.markdown("#### Upgrades brought to this race")
    if not r:
        st.caption("Part-by-part lists start at Monza. For Australia to the Dutch GP only season totals were published; see Tech upgrades for those.")
    else:
        counts = pd.Series(r["counts"]).sort_values(ascending=False)
        flag = " (approximate)" if "approx" in r["src"] else (" (reported, not checked against the FIA list)" if "reported" in r["src"] else "")
        st.markdown(f"<div class='hc hc-tab' style='min-height:0'><div class='hc-k'>{html.escape(r['label'])}{flag}</div>"
                    f"<div class='hc-big'>{int(counts.sum())} new parts</div><div class='hc-sub'>Most: {html.escape(counts.index[0])} ({int(counts.iloc[0])})</div></div>",
                    unsafe_allow_html=True)
        blocks = ""
        for t in counts.index:
            parts = (r.get("items") or {}).get(t) or []
            lis = "".join(f"<li>{html.escape(p)}</li>" for p in parts) or "<li class='hc-dim'>No new parts declared.</li>"
            blocks += (f"<div class='upc' style='border-left-color:{extras_pages._team_colour(t, grid)}'><div class='upc-t'>{html.escape(t)} "
                       f"<span class='hc-dim'>{int(counts[t])} declared</span></div><ul>{lis}</ul></div>")
        st.markdown(f"<div class='upc-grid'>{blocks}</div>{extras_pages.UP_CSS}", unsafe_allow_html=True)
        none = [t for t in d["upgrades"]["teams"] if not r["counts"].get(t)]
        if none:
            st.caption(f"No new parts declared at {r['label']}: {', '.join(none)}.")
    latest_section(d, grid, r)
    all_section(d, grid, r)
    pace_section(raw, model, r, grid, focus)


def history(d, team, upto=None):
    rounds = d["upgrades"]["rounds"]
    if upto is not None:
        rounds = rounds[:rounds.index(upto) + 1]
    out = []
    for rr in rounds[::-1]:
        parts = (rr.get("items") or {}).get(team) or []
        n = int(rr["counts"].get(team, 0))
        if parts or n:
            out.append({"round": rr["label"], "count": n, "parts": parts, "src": rr["src"]})
    return out


def all_section(d, grid, r):
    tot = extras_pages.upgrade_totals(d)
    with st.expander("All upgrades by every team this season", expanded=True):
        pick = st.multiselect("Teams", list(tot.index), default=list(tot.index), key="pf_up_teams")
        blocks = ""
        for t in [x for x in tot.index if x in pick]:
            rows = history(d, t, r)
            body = ""
            for h in rows:
                lis = "".join(f"<li>{html.escape(p)}</li>" for p in h["parts"]) or f"<li class='hc-dim'>{h['count']} parts (no list published)</li>"
                body += f"<div class='hc-dim' style='font-size:.68rem;margin-top:.35rem'>{html.escape(h['round'])} · {h['count']}</div><ul>{lis}</ul>"
            blocks += (f"<div class='upc' style='border-left-color:{extras_pages._team_colour(t, grid)}'><div class='upc-t'>{html.escape(t)} "
                       f"<span class='hc-dim'>{sum(h['count'] for h in rows)} new parts</span></div>{body or '<ul><li class=hc-dim>None declared.</li></ul>'}</div>")
        st.markdown(f"<div class='upc-grid'>{blocks}</div>", unsafe_allow_html=True)
        st.caption("Newest first, up to the race picked above. Part-by-part lists start at Monza; Australia to the Dutch GP shows totals only. "
                   "Source: FIA car presentation submissions as reported by RACER and others (see Tech upgrades for links).")


def latest_upgrades(d, upto=None):
    rounds = d["upgrades"]["rounds"]
    if upto is not None:
        rounds = rounds[:rounds.index(upto) + 1]
    tot = extras_pages.upgrade_totals({"upgrades": {"teams": d["upgrades"]["teams"], "rounds": rounds}})
    out = []
    for t in tot.index:
        last = next((r for r in rounds[::-1] if r.get("items") and (r["items"].get(t) or [])), None)
        out.append({"team": t, "total": int(tot[t]), "round": last["label"] if last else None, "parts": (last["items"][t] if last else [])})
    return out


def latest_section(d, grid, r):
    rows = latest_upgrades(d, r)
    st.markdown("#### Every team's latest upgrades")
    blocks = ""
    for x in rows:
        if x["parts"]:
            lis = "".join(f"<li>{html.escape(p)}</li>" for p in x["parts"])
            head = f"{html.escape(x['round'])} · {len(x['parts'])} parts"
        else:
            lis, head = "<li class='hc-dim'>No part-by-part list since Monza.</li>", "—"
        blocks += (f"<div class='upc' style='border-left-color:{extras_pages._team_colour(x['team'], grid)}'><div class='upc-t'>{html.escape(x['team'])} "
                   f"<span class='hc-dim'>{head}</span></div><ul>{lis}</ul><div class='hc-dim' style='font-size:.66rem'>{x['total']} new parts this season so far</div></div>")
    st.markdown(f"<div class='upc-grid'>{blocks}</div>", unsafe_allow_html=True)
    st.caption("The most recent race where each team declared new parts to the FIA, up to the race picked above. Season totals count every round from Australia.")


def pace_section(raw, model, rnd, grid, focus=()):
    st.markdown("#### Race pace by team")
    team = rv.teams(raw)
    drv = model["driver"]
    if drv.empty or not team:
        st.caption("Not enough clean laps to compare the cars.")
        return
    df = pd.DataFrame({"num": drv.index.astype(int), "pace": drv.values})
    df["team"] = df["num"].map(team)
    laps = rv.lap_table(raw)
    trap = laps.groupby("driver_number")["st_speed"].max() if "st_speed" in laps else pd.Series(dtype=float)
    df["trap"] = df["num"].map(trap)
    t = df.dropna(subset=["team"]).groupby("team").agg(pace=("pace", "mean"), trap=("trap", "max")).sort_values("pace")
    t["gap"] = t["pace"] - t["pace"].min()
    counts = (rnd or {}).get("counts") or {}

    def parts(name):
        key = next((k for k in counts if extras_pages._team_colour(k, grid) == extras_pages._team_colour(name, grid)), None)
        return counts.get(key) if key else None

    colours = {tm: c for n, c in rv.colours(raw).items() for tm in [team.get(n)] if tm}
    mine = {team.get(n) for n in focus}
    labels = [f"+{g:.2f}s" + (f" · {parts(n)} new parts" if parts(n) is not None else "") for n, g in zip(t.index, t["gap"])]
    fig = go.Figure(go.Bar(x=t["gap"][::-1], y=t.index[::-1], orientation="h", text=labels[::-1], textposition="outside",
                           marker_color=[colours.get(n, "#9A9AA8") for n in t.index[::-1]],
                           marker_line=dict(color=["#FFFFFF" if n in mine else "rgba(0,0,0,0)" for n in t.index[::-1]], width=2),
                           hovertext=[f"{n}: top speed {s:.0f} km/h" if pd.notna(s) else n for n, s in zip(t.index[::-1], t["trap"][::-1])], hoverinfo="text"))
    fig.update_layout(xaxis_title="Seconds a lap slower than the fastest car", xaxis_range=[0, max(t["gap"].max() * 1.6, 0.5)], showlegend=False)
    st.plotly_chart(_chart(fig, 40 + 34 * len(t)), use_container_width=True, config={"displayModeBar": False})
    st.caption("Race pace = each driver's typical gap on clean laps once tyre type, tyre age, fuel and the weather on that lap are taken out; "
               "a team is the average of its two drivers; the teams of the two drivers you picked are outlined. Hover for each team's top speed at the speed trap. Estimates from OpenF1 lap times.")


def weather_chart(state, rain):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    run = None
    for _, r in state.iterrows():
        if run and run[0] == r["cond"]:
            run[2] = r["lap"]
            continue
        if run:
            fig.add_vrect(x0=run[1] - .5, x1=run[2] + .5, fillcolor=COND_COLOUR[run[0]], line_width=0, layer="below")
        run = [r["cond"], r["lap"], r["lap"]]
    if run:
        fig.add_vrect(x0=run[1] - .5, x1=run[2] + .5, fillcolor=COND_COLOUR[run[0]], line_width=0, layer="below")
    fig.add_trace(go.Scatter(x=state["lap"], y=state["wet_share"] * 100, name="Cars on inters or wets (%)", line=dict(color="#43B02A", width=2.2),
                             hovertemplate="Lap %{x}: %{y:.0f}% on wet tyres<extra></extra>"))
    if len(rain):
        wet = rain[rain["rain"]]
        fig.add_trace(go.Scatter(x=wet["lap"], y=[104] * len(wet), mode="markers", name="Rain falling", marker=dict(symbol="line-ns-open", size=12, color="#5AB4FF"),
                                 hovertemplate="Lap %{x}: rain<extra></extra>"))
        fig.add_trace(go.Scatter(x=rain["lap"], y=rain["track"], name="Track °C", line=dict(color="#FF8C42", width=1.4, dash="dot"),
                                 hovertemplate="Lap %{x}: track %{y:.0f}°C<extra></extra>"), secondary_y=True)
    fig.update_yaxes(title_text="% of cars on wet tyres", range=[0, 110], secondary_y=False)
    fig.update_yaxes(title_text="Track °C", secondary_y=True, showgrid=False)
    fig.update_xaxes(title_text="Lap")
    return _chart(fig, 300)


def model_table(m):
    rows = ""
    for k in sim.CONDS:
        if not (m["state"]["cond"] == k).any():
            continue
        for c in sim.COMPOUNDS:
            d, w = m["delta"][(c, k)], m["wear"][(c, k)]
            dot = f"<i class='ty-dot' style='background:{duel.COMPOUND_COLOUR[c]}'></i>"
            laps_k = [lap for lap, kk in m["cond"].items() if kk == k]
            if sim.family(c) != sim.MAJOR[k]:
                g = [m["gap"][lap] for lap in laps_k]
                meas = sum(m["gap_src"][lap] == "measured" for lap in laps_k)
                pace = "+%.1f to +%.1fs" % (min(g) + d, max(g) + d) if g else "—"
                src = f"changes lap by lap: measured on {meas} of {len(laps_k)} laps, estimate on the rest"
            else:
                pace = "best" if abs(d) < 0.005 else "%+.2fs" % d
                src = f"pace {m['pace_src'][(c, k)]}"
            rows += (f"<tr><td>{sim.COND_NAME[k]}</td><td>{dot}{c.title()}</td><td>{pace}</td><td>{w:.3f}s</td>"
                     f"<td class='duel-dim'>{src}; wear {m['wear_src'][(c, k)]}</td></tr>")
    return (f"<table class='duel-t'><tr><th>Track</th><th>Tyre</th><th>Pace vs best tyre (new set)</th><th>Wear per lap</th><th>Source</th></tr>{rows}</table>")


def strategy_section(race, raw, laps, sk, code, colour, present, num, rival=None):
    m, starts, top = model_for(sk)
    rain = pd.DataFrame()
    try:
        rain = sim.rain_by_lap(weather(sk), laps)
    except Exception:
        pass
    st.markdown("#### Weather and track")
    st.plotly_chart(weather_chart(m["state"], rain), use_container_width=True, config={"displayModeBar": False})
    n_cond = m["state"]["cond"].value_counts()
    st.caption("Shading: grey = dry, green = damp (most cars on inters), blue = wet (most cars on full wets). The track condition each lap comes from what tyres the field ran; "
               "rain and track temperature from OpenF1's weather station. "
               + ", ".join(f"{sim.COND_NAME[k]}: {int(n_cond.get(k, 0))} laps" for k in sim.CONDS if n_cond.get(k)))
    who = code.get(num, str(num))
    st.markdown(f"#### Best tyre strategy · {html.escape(race['name'])}")
    act = sim.actual_plan(raw, num, m["total"])
    act_t = sim.plan_time(m, act) if act else None
    best = starts[0]
    rows = ""
    for p in starts:
        dot = f"<i class='ty-dot' style='background:{duel.COMPOUND_COLOUR[p['compounds'][0]]}'></i>"
        gap = "fastest" if p["time"] - best["time"] < 0.05 else f"+{p['time'] - best['time']:.1f}s"
        rows += f"<tr><td>{dot}{p['compounds'][0].title()}</td><td>{html.escape(sim.describe(p))}</td><td>{p['stops']}</td><td>{gap}</td></tr>"
    st.markdown(f"<table class='duel-t'><tr><th>Start on</th><th>Best plan</th><th>Stops</th><th>Race time</th></tr>{rows}</table>", unsafe_allow_html=True)
    rows = ""
    for n in [num] + ([rival] if rival and rival != num else []):
        a = sim.actual_plan(raw, n, m["total"])
        if not a:
            continue
        lost = sim.plan_time(m, a) - best["time"]
        cls = whatif.reclassify(laps, n, lost)
        pos = _pos(raw, n)
        passed = ", ".join(code.get(d, str(d)) for d, _ in cls["passed"]) if cls else ""
        fin = f"P{pos} → P{pos - cls['places']}" if pos and cls else "—"
        rows += (f"<tr><td><i class='ty-dot' style='background:{colour.get(n, '#9A9AA8')}'></i><b>{html.escape(code.get(n, str(n)))}</b></td>"
                 f"<td>{html.escape(sim.describe(a))}</td><td>{'%.1fs' % max(lost, 0)}</td><td>{fin}"
                 f"<span class='duel-dim'>{' · ahead of ' + html.escape(passed) if passed else ''}</span></td></tr>")
    if rows:
        st.markdown(f"<table class='duel-t'><tr><th>Driver</th><th>What they ran</th><th>Time lost vs best plan</th><th>Finish with the best plan</th></tr>{rows}</table>",
                    unsafe_allow_html=True)
    st.markdown("##### Top plans overall")
    items = []
    for i, p in enumerate(top[:5]):
        gap = "fastest" if i == 0 else "+%.1fs" % (p["time"] - top[0]["time"])
        items.append(f"<li>{html.escape(sim.describe(p))} · {p['stops']} stop{'s' if p['stops'] != 1 else ''} · {gap}</li>")
    st.markdown("<ul class='duel-list'>" + "".join(items) + "</ul>", unsafe_allow_html=True)
    build_your_own(m, act, act_t, laps, raw, num, who, code, sk)
    with st.expander("The tyre model for this race"):
        st.markdown(model_table(m), unsafe_allow_html=True)
        st.caption(f"Pit stop cost: {m['pit_loss']:.1f}s (middle value of every stop in this race: slow lap in plus slow lap out). "
                   "Each lap's time = the lap's base time (track grip, fuel and weather that lap) + the tyre's pace gap in that condition + wear per lap × tyre age. "
                   "Gaps are measured from cars on different tyres on the same lap. Where nobody ran a tyre in a condition, an estimate is used and marked. "
                   "All plans assume new sets, clear track and no Safety Car. Dry races need two different dry tyres unless inters or wets are used.")


def build_your_own(m, act, act_t, laps, raw, num, who, code, sk):
    st.markdown("##### Build your own strategy")
    n = m["total"]
    default = act or {"compounds": ["SOFT", "MEDIUM"], "pits": [n // 2]}
    stops = st.select_slider("Pit stops", options=[0, 1, 2, 3], value=min(len(default["pits"]), 3), key=f"pf_stops_{sk}_{num}")
    cols = st.columns(stops + 1)
    comps, pits = [], []
    for i in range(stops + 1):
        dc = default["compounds"][i] if i < len(default["compounds"]) else "MEDIUM"
        comps.append(cols[i].selectbox(f"Stint {i + 1}", sim.COMPOUNDS, index=sim.COMPOUNDS.index(dc) if dc in sim.COMPOUNDS else 1,
                                       format_func=str.title, key=f"pf_c{i}_{sk}_{num}"))
        if i < stops:
            dp = default["pits"][i] if i < len(default["pits"]) else min(n - 1, (i + 1) * n // (stops + 1))
            pits.append(cols[i].number_input("Pit on lap", 1, n - 1, int(dp), key=f"pf_p{i}_{sk}_{num}"))
    plan = {"compounds": comps, "pits": pits}
    if sorted(set(pits)) != pits:
        st.caption("Pit laps need to go up stint by stint.")
        return
    t = sim.plan_time(m, plan)
    msg = []
    if not sim.legal(comps):
        msg.append("Not allowed in a dry race: you must use two different dry tyres unless you fit inters or wets.")
    if act_t is not None:
        saved = act_t - t
        cls = whatif.reclassify(laps, num, saved)
        pos = _pos(raw, num)
        fin = f" Finish: P{pos} → P{pos - cls['places']}." if pos and cls else ""
        msg.insert(0, f"{abs(saved):.1f}s {'faster' if saved > 0 else 'slower'} than what {who} really did.{fin}")
    st.markdown(f"<div class='duel-head'>{html.escape(' '.join(msg))}</div>", unsafe_allow_html=True)


def _pos(raw, num):
    res = raw.get("session_result")
    try:
        return int(res[res["driver_number"] == num]["position"].iloc[0])
    except Exception:
        return None


def _card(col, k, v, sub, colr):
    col.markdown(f"<div class='duel-card' style='border-left-color:{colr}'><div class='duel-k'>{k}</div><div class='duel-v' style='font-size:1rem'>{v}</div>"
                 f"<div class='duel-dim' style='font-size:.68rem'>{sub}</div></div>", unsafe_allow_html=True)


def page():
    st.markdown(CSS + DUEL_CSS, unsafe_allow_html=True)
    st.subheader("Performance")
    if os.environ.get("F1_REVIEW_FETCH", "1") == "0":
        st.caption("Race data is switched off here.")
        return
    try:
        rs = races()
    except Exception:
        rs = []
    if not rs:
        st.warning("Couldn't load the race list from OpenF1 just now. Try again in a minute.")
        return
    c1, c2, c3 = st.columns(3)
    race = c1.selectbox("Race", rs[::-1], format_func=lambda r: f"R{r['round']} · {r['name']}", key="pf_race")
    from f1analytics.ui.review_panel import fetch

    try:
        raw = fetch(race["key"])
    except Exception:
        st.warning("Couldn't load this race from OpenF1 just now. Try again in a minute.")
        return
    laps = rv.lap_table(raw)
    if laps.empty:
        st.caption("No lap data for this race yet.")
        return
    code, colour = rv.codes(raw), rv.colours(raw)
    present = sorted(set(laps["driver_number"]) & set(code), key=lambda n: code[n])
    by_code = {v: k for k, v in code.items()}
    key = f"pf_drv_{race['key']}"
    if st.session_state.get(key) not in present:
        st.session_state[key] = by_code.get(focus_code(), present[0])
    num = c2.selectbox("Driver", present, format_func=code.get, key=key)
    team = rv.teams(raw)
    others = [n for n in present if n != num]
    mate = next((n for n in others if team.get(n) and team.get(n) == team.get(num)), others[0] if others else num)
    rkey = f"pf_riv_{race['key']}_{num}"
    if st.session_state.get(rkey) not in others:
        st.session_state[rkey] = mate
    rival = c3.selectbox("Compare with", others, format_func=code.get, key=rkey) if others else None
    try:
        m, _, _ = model_for(race["key"])
    except Exception:
        m = None
    t1, t2, t3 = st.tabs(["Upgrades & pace", "Tyre strategy & weather", "What if"])
    with t1:
        if m is not None:
            upgrades_section(race, raw, m, [n for n in (num, rival) if n is not None])
    with t2:
        try:
            strategy_section(race, raw, laps, race["key"], code, colour, present, num, rival)
        except Exception:
            import logging

            logging.getLogger("f1analytics").exception("strategy failed")
            st.warning("The strategy model hit a snag for this race.")
    with t3:
        from f1analytics.ui.whatif_panel import whatif_tab

        try:
            whatif_tab(raw, laps, race["key"], code, colour, present, num)
        except Exception:
            import logging

            logging.getLogger("f1analytics").exception("what if failed")
            st.warning("The what-if view hit a snag for this race.")
