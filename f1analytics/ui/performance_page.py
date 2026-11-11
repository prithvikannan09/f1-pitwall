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
from f1analytics.ui.mobile import how

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
        st.caption("Part-by-part lists start at Monza. For Australia to the Dutch GP only season totals were published; see the season table above for those.")
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
                   "Source: FIA car presentation submissions as reported by RACER and others (links at the bottom of this tab).")


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
    how("Race pace = each driver's typical gap on clean laps once tyre type, tyre age, fuel and the weather on that lap are taken out; "
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
    how("Shading: grey = dry, green = damp (most cars on inters), blue = wet (most cars on full wets). The track condition each lap comes from what tyres the field ran; "
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
    t1, t2, t3, t5 = st.tabs(["Upgrades & pace", "Tyre strategy & weather", "What if", "Season: driver form"])
    with t5:
        try:
            driver_form_tab(code.get(num))
        except Exception:
            import logging

            logging.getLogger("f1analytics").exception("driver form failed")
            st.warning("The driver form view hit a snag.")
    with t1:
        if m is not None:
            d = extras_pages.load()
            rnd = round_for(race, d["upgrades"]["rounds"])
            grid = extras_pages._grid()
            try:
                upgrade_impact_section(race, raw, d, rnd, grid, num, rival, code, colour)
            except Exception:
                import logging

                logging.getLogger("f1analytics").exception("upgrade impact failed")
            pace_section(raw, m, rnd, grid, [n for n in (num, rival) if n is not None])
            if rival is not None:
                telemetry_compare(race, raw, laps, num, rival, code, colour, rnd)
            st.caption("Season totals, every team's full upgrade list and engine components are on the 🔧 Upgrades page.")
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


def _season_data():
    from f1analytics.pitwall.racecraft import load

    return load()


@st.cache_data(ttl=3 * 3600, show_spinner="Loading the season results…")
def season_results(year=YEAR):
    from f1analytics.pitwall import season as ss

    return ss.results(year)


def season_upgrades_tab(team_colours, focus_teams=()):
    from f1analytics.pitwall import season_form as sf

    data = _season_data()
    if not data:
        st.caption("Season pace data isn't available.")
        return
    races = data["races"]
    pace = sf.team_pace(data)
    events = sf.upgrade_events(extras_pages.load(), races)
    v = sf.verdicts(pace, events)
    st.markdown("#### Did the upgrades work?")
    rows = ""
    for _, r in v.iterrows():
        col = team_colours.get(r["team"], "#9A9AA8")
        tone = "#43B02A" if r["verdict"] == "Closed the gap" else ("#E10600" if r["verdict"] == "Fell back" else "#9A9AA8")
        rows += (f"<tr><td><i class='ty-dot' style='background:{col}'></i>{html.escape(r['team'])}</td><td>{r['parts']}</td>"
                 f"<td>{r['early']:.2f}%</td><td>{r['recent']:.2f}%</td><td style='color:{tone}'>{r['change']:+.2f}% · {r['verdict']}</td></tr>")
    st.markdown(f"<table class='duel-t'><tr><th>Team</th><th>New parts</th><th>Gap to fastest, first 5 races</th><th>Last 5 races</th><th>Change</th></tr>{rows}</table>",
                unsafe_allow_html=True)
    teams = list(v["team"])
    default = next((t for t in teams if t in focus_teams), teams[0])
    team = st.selectbox("Team", teams, index=teams.index(default), key="pf_season_team")
    g = pace[pace["team"] == team].sort_values("race")
    e = events[(events["team"] == team) & events["race"].notna()]
    names = [r["location"] for r in races]
    col = team_colours.get(team, "#E10600")
    upgrade_line_chart([(team, list(g["race"]), list(g["gap"]), col)], {team: e}, names, f"{team}: gap to the fastest car",
                       "% off fastest", True, None, "pf_season_range", "%", "{:.2f}%")
    pre = events[(events["team"] == team) & events["race"].isna()]["parts"].sum()
    if pre:
        st.caption(f"{team} also declared {int(pre)} new parts between Australia and the Dutch GP, but only a season total was published for those races, so they can't be placed on the chart.")
    effects = sf.event_effect(pace, events, team)
    if effects:
        lines = []
        for x in effects:
            if x["change"] is None:
                lines.append(f"<li><b>{html.escape(x['label'])}</b> · {x['parts']} parts · not enough races yet to judge.</li>")
                continue
            word = "faster" if x["change"] < 0 else "slower"
            parts = html.escape(", ".join(x["items"][:4]) + ("…" if len(x["items"]) > 4 else ""))
            lines.append(f"<li><b>{html.escape(x['label'])}</b> · {x['parts']} parts · {x['before']:.2f}% → {x['after']:.2f}%: "
                         f"<b>{abs(x['change']):.2f}% {word}</b> relative to the field. <span class='duel-dim'>{parts}</span></li>")
        st.markdown("##### Each upgrade, before and after")
        st.markdown("<ul class='duel-list'>" + "".join(lines) + "</ul>", unsafe_allow_html=True)
    how("Pace = the faster of the team's two drivers on clean race laps, as a % gap to the fastest car that race. Before = up to 3 races before the upgrade, "
               "after = that race and the next 2. It's relative: if everyone else upgrades more, a team can fall back even after bringing parts. "
               "Track type changes the order too (a car good at Monaco may struggle at Monza), so read a single race with care. Estimates from OpenF1 lap times; "
               "upgrade lists from the FIA submissions as reported.")


def driver_form_tab(focus=None):
    from f1analytics.pitwall import season_form as sf

    try:
        res = season_results()
    except Exception:
        res = None
    if res is None or res.empty:
        st.warning("Couldn't load the season results just now.")
        return
    data = _season_data() or {}
    form = sf.driver_form(res, sf.pace_halves(data))
    half = form.attrs.get("half")
    rounds = form.attrs.get("rounds", [])
    st.markdown("#### Who started strong and who faded")
    st.caption(f"First half = rounds 1 to {half}; second half = rounds {half + 1} to {rounds[-1] if rounds else ''}.")
    for label, tone in (("Finishing strong", "#43B02A"), ("Started strong, faded", "#E10600")):
        x = form[form["form"] == label].sort_values("ppr_change", ascending=label != "Finishing strong")
        if len(x):
            names = ", ".join(f"{r['code']} ({r['ppr_first']:.1f} → {r['ppr_second']:.1f} pts a race)" for _, r in x.iterrows())
            st.markdown(f"<div class='duel-card' style='border-left-color:{tone}'><div class='duel-k'>{label}</div><div style='font-size:.82rem'>{html.escape(names)}</div></div>",
                        unsafe_allow_html=True)
    rows = ""
    for _, r in form.iterrows():
        tone = "#43B02A" if r["form"] == "Finishing strong" else ("#E10600" if r["form"] != "Steady" else "#9A9AA8")
        pf = "" if pd.isna(r["pace_first"]) or pd.isna(r["pace_second"]) else f"{r['pace_first']:.2f}% → {r['pace_second']:.2f}%"
        me = " style='background:rgba(225,6,0,.12)'" if r["code"] == focus else ""
        rows += (f"<tr{me}><td><b>{html.escape(r['code'])}</b> <span class='duel-dim'>{html.escape(str(r['team']))}</span></td><td>{r['points']:.0f}</td>"
                 f"<td>{r['ppr_first']:.1f} → {r['ppr_second']:.1f}</td><td>P{r['fin_first']:.1f} → P{r['fin_second']:.1f}</td>"
                 f"<td>{r['dnf_first']} → {r['dnf_second']}</td><td>{pf}</td><td style='color:{tone}'>{r['form']}</td></tr>")
    st.markdown(f"<div style='overflow-x:auto'><table class='duel-t'><tr><th>Driver</th><th>Points</th><th>Points a race</th><th>Average finish</th>"
                f"<th>DNFs</th><th>Race pace vs fastest</th><th>Form</th></tr>{rows}</table></div>", unsafe_allow_html=True)
    cum = sf.cumulative_points(res)
    top = list(form["code"].head(6))
    if focus and focus in cum.columns and focus not in top:
        top.append(focus)
    pick = st.multiselect("Drivers on the chart", list(form["code"]), default=top, key="pf_form_drivers")
    colours = {}
    try:
        from f1analytics.ui.season_pages import colours as season_colours

        colours = season_colours()
    except Exception:
        pass
    fig = go.Figure()
    for c in pick:
        if c in cum.columns:
            fig.add_trace(go.Scatter(x=cum.index, y=cum[c], name=c, mode="lines", line=dict(color=colours.get(c), width=3 if c == focus else 1.8),
                                     hovertemplate=f"{c} after round %{{x}}: %{{y:.0f}} pts<extra></extra>"))
    if half:
        fig.add_vline(x=half + 0.5, line_color="#55556A", line_dash="dot", annotation_text="half way", annotation_font_size=9)
    fig.update_layout(title="Points through the season", xaxis_title="Round", yaxis_title="Points")
    st.plotly_chart(_chart(fig, 380), use_container_width=True, config={"displayModeBar": False})
    order = list(form["code"])
    pos = res.assign(fin=[int(x["position"]) if str(x["text"]).isdigit() else None for _, x in res.iterrows()])
    grid = pos.pivot_table(index="code", columns="round", values="fin", aggfunc="first").reindex(order)
    txt = res.assign(t=[str(x["position"]) if str(x["text"]).isdigit() else "DNF" for _, x in res.iterrows()]).pivot_table(
        index="code", columns="round", values="t", aggfunc="first").reindex(order)
    heat = go.Figure(go.Heatmap(z=grid.values, x=[f"R{c}" for c in grid.columns], y=grid.index, text=txt.values, texttemplate="%{text}",
                                colorscale=[[0, "#43B02A"], [0.25, "#FFD12E"], [0.5, "#E87722"], [1, "#2E2E3A"]], zmin=1, zmax=22, showscale=False,
                                hovertemplate="%{y} round %{x}: %{text}<extra></extra>"))
    heat.update_yaxes(autorange="reversed")
    heat.update_layout(title="Every finish this season (green = podium, grey = back of the field or DNF)")
    st.plotly_chart(_chart(heat, 40 + 22 * len(order)), use_container_width=True, config={"displayModeBar": False})
    how("Points and finishes: Jolpica (Ergast). DNF counts as P22 in the average finish. Race pace vs fastest: middle value of each driver's clean-lap pace "
               "as a % gap to the fastest driver that race (OpenF1), so it shows speed separately from luck and reliability. "
               "Form: 'faded' or 'finishing strong' means at least 3 points a race up or down between the two halves, or 1.5 points plus two places on average.")



def _fmt(v, unit, digits=2, sign=True):
    if v is None or pd.isna(v):
        return "—"
    return (f"{v:+.{digits}f}" if sign else f"{v:.{digits}f}") + unit


def upgrade_impact_section(race, raw, d, rnd, grid, num, rival, code, colour):
    from f1analytics.pitwall import season_form as sf

    st.markdown("#### Upgrades at this race and did they work?")
    if not rnd:
        st.caption("Part-by-part upgrade lists start at Monza, so there's no per-race breakdown for this track. Pick Monza or later.")
        return
    data = _season_data() or {}
    ri = sf.race_index(data, race["key"])
    events = sf.upgrade_events(d, data.get("races") or [])
    team = rv.teams(raw)
    mine = {sf.team_name(team.get(n)) for n in (num, rival) if n is not None and team.get(n)}
    counts = pd.Series(rnd["counts"]).sort_values(ascending=False)
    counts = counts[counts > 0]
    none = [t for t in d["upgrades"]["teams"] if t not in counts.index]
    if counts.empty:
        st.caption(f"No team declared new parts at {rnd['label']}.")
    impact = {x["team"]: x for x in sf.impact_at(data, events, ri)} if ri is not None else {}
    cards = ""
    for t in counts.index:
        x = impact.get(t, {})
        parts = (rnd.get("items") or {}).get(t) or []
        lis = "".join(f"<li>{html.escape(p)}</li>" for p in parts) or f"<li class='hc-dim'>{int(counts[t])} parts (no list)</li>"
        pb, ph, pa = x.get("pace_before"), x.get("pace_here"), x.get("pace_after")
        verdict = ""
        if pb is not None and pa is not None:
            ch = pa - pb
            verdict = ("<b style='color:#43B02A'>Faster after</b>" if ch <= -0.15 else "<b style='color:#E10600'>Slower after</b>" if ch >= 0.15
                       else "<b>No clear change</b>") + f" · gap to fastest {pb:.2f}% → {pa:.2f}%"
            if x.get("races_after", 0) < 2:
                verdict += " <span class='hc-dim'>(only this race so far)</span>"
        tel = []
        for c, name in (("corner_speed_kmh", "corner speed"), ("top_speed_kmh", "top speed")):
            b0, a0 = x.get(f"{c}_before"), x.get(f"{c}_after")
            if b0 is not None and a0 is not None:
                tel.append(f"{name} vs field {b0:+.1f} → {a0:+.1f} km/h")
        ring = "outline:1px solid #F3F3F5;" if t in mine else ""
        cards += (f"<div class='upc' style='{ring}border-left-color:{extras_pages._team_colour(t, grid)}'><div class='upc-t'>{html.escape(t)} "
                  f"<span class='hc-dim'>{int(counts[t])} new parts</span></div><ul>{lis}</ul>"
                  f"<div style='font-size:.7rem;margin-top:.3rem'>{verdict}</div><div class='hc-dim' style='font-size:.66rem'>{' · '.join(tel)}</div></div>")
    if cards:
        st.markdown(f"<div class='upc-grid'>{cards}</div>{extras_pages.UP_CSS}", unsafe_allow_html=True)
    if none:
        st.caption(f"No new parts at {rnd['label']}: {', '.join(none)}.")
    how("Before = the 3 races before this one; after = this race and the next 2. Gap to fastest is race pace on clean laps; corner and top speed are "
               "telemetry (OpenF1, about 4 samples a second) compared with the field median at each braking zone and straight, so different tracks can be compared. "
               "Estimates; a single race can be skewed by weather or track type.")
    if mine and ri is not None:
        trend_chart(data, events, sorted(mine), ri)
    try:
        from f1analytics.ui.upgrades_page import aduo_section

        aduo_section(mine, compact=True)
    except Exception:
        pass


def trend_chart(data, events, teams, ri):
    from f1analytics.pitwall import season_form as sf

    tel = sf.team_metrics(data)
    pace = sf.team_pace(data)
    names = [r["location"] for r in data["races"]]
    cols = {}
    try:
        from f1analytics.ui.upgrades_page import team_colours

        cols = team_colours()
    except Exception:
        pass
    metric = st.radio("Show", ["Gap to fastest car", "Corner speed vs field", "Top speed vs field"], horizontal=True, key="pf_trend_metric")
    lines, evs = [], {}
    for t in teams:
        if metric == "Gap to fastest car":
            g = pace[pace["team"] == t].sort_values("race")
            y = g["gap"]
        else:
            g = tel[tel["team"] == t].sort_values("race")
            y = g["corner_speed_kmh" if metric.startswith("Corner") else "top_speed_kmh"]
        lines.append((t, list(g["race"]), list(y), cols.get(t, "#9A9AA8")))
        evs[t] = events[(events["team"] == t) & events["race"].notna()]
    gap = metric == "Gap to fastest car"
    upgrade_line_chart(lines, evs, names, f"{' vs '.join(teams)}: {metric.lower()}", "%" if gap else "km/h", gap, ri, "pf_trend_range",
                       "%" if gap else " km/h", "{:.2f}%" if gap else "{:+.1f} km/h")
    how("Dots under the chart = races where that team declared new parts; bigger dot, more parts. The dotted line is the race you picked. "
        "Higher speed and a smaller gap are better. Speeds are compared with the field median at each braking zone and straight.")


def upgrade_line_chart(lines, events, names, title, ytitle, reverse, mark, key, unit, fmt):
    from f1analytics.ui.mobile import code as rcode

    span = st.radio("Races", ["Last 10", "Whole season"], horizontal=True, key=key, label_visibility="collapsed")
    lo = max(0, len(names) - 10) if span == "Last 10" else 0
    codes = [rcode(n) for n in names]
    shown = codes[lo:]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.8, 0.2], vertical_spacing=0.05)
    for name, xs, ys, colr in lines:
        pts = [(codes[int(x)], y, names[int(x)]) for x, y in zip(xs, ys) if int(x) >= lo]
        fig.add_trace(go.Scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], name=name, mode="lines+markers", line=dict(color=colr, width=2.4),
                                 marker=dict(size=6), customdata=[p[2] for p in pts],
                                 hovertemplate="%{customdata}: %{y:.2f}" + unit + "<extra>" + name + "</extra>"), row=1, col=1)
    for k, (name, _, _, colr) in enumerate(lines):
        e = events.get(name)
        if e is None or not len(e):
            continue
        e = e[e["race"].astype(int) >= lo]
        fig.add_trace(go.Scatter(x=[codes[int(r)] for r in e["race"]], y=[k] * len(e), mode="markers", showlegend=False,
                                 marker=dict(size=[6 + min(int(p), 6) * 2 for p in e["parts"]], color=colr, line=dict(color="#101016", width=1)),
                                 customdata=e["parts"], hovertemplate="%{x}: %{customdata} new parts<extra>" + name + "</extra>"), row=2, col=1)
    if mark is not None and int(mark) >= lo:
        for r in (1, 2):
            fig.add_vline(x=codes[int(mark)], line_color="#F3F3F5", line_dash="dot", line_width=1, row=r, col=1)
    fig.update_xaxes(categoryorder="array", categoryarray=shown, tickangle=0, tickfont=dict(size=9))
    fig.update_yaxes(title_text=ytitle, row=1, col=1, autorange="reversed" if reverse else True)
    fig.update_yaxes(row=2, col=1, showticklabels=False, showgrid=False, range=[-0.7, max(len(lines) - 0.3, 0.7)], title_text="parts", title_font=dict(size=9))
    fig.update_layout(title=title)
    st.plotly_chart(_chart(fig, 330), use_container_width=True, config={"displayModeBar": False})


def telemetry_compare(race, raw, laps, num, rival, code, colour, rnd):
    from f1analytics.pitwall.season_form import team_name
    from f1analytics.ui.duel_panel import telemetry_section

    team = rv.teams(raw)
    ca, cb = code.get(num, str(num)), code.get(rival, str(rival))
    col_a, col_b = colour.get(num, "#E10600"), colour.get(rival, "#3671C6")
    if col_a.lower() == col_b.lower():
        col_b = "#9A9AA8"
    st.markdown(f"#### Telemetry at {html.escape(race['location'])}: {html.escape(ca)} vs {html.escape(cb)}")
    notes = []
    for n, c in ((num, ca), (rival, cb)):
        t = team_name(team.get(n, ""))
        key = next((k for k in ((rnd or {}).get("counts") or {}) if team_name(k) == t or k == t), None)
        parts = ((rnd or {}).get("items") or {}).get(key) or [] if key else []
        cnt = ((rnd or {}).get("counts") or {}).get(key, 0) if key else 0
        notes.append(f"{c} ({t}): " + (f"{cnt} new parts here ({', '.join(parts[:4])}{'…' if len(parts) > 4 else ''})" if cnt else "no new parts here"))
    st.caption(" · ".join(notes))
    telemetry_section(raw, laps, race["key"], num, rival, ca, cb, col_a, col_b)
