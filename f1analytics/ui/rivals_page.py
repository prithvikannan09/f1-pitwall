import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from f1analytics.pitwall import rivalry as rv
from f1analytics.ui import glossary as gl

TEAM_COLOURS = {"ferrari": "#E80020", "red bull": "#3671C6", "mercedes": "#27F4D2", "mclaren": "#FF8000", "aston": "#229971", "alpine": "#0093CC",
                "williams": "#64C4FF", "haas": "#B6BABD", "sauber": "#52E252", "kick": "#52E252", "audi": "#F50537", "racing bulls": "#6692FF",
                "rb ": "#6692FF", "alphatauri": "#5E8FAA", "alfa": "#C92D4B", "cadillac": "#AAAAAD"}
FONT = dict(family="Titillium Web, sans-serif", color="#F3F3F5")

CSS = """
<style>
.rv-score{background:var(--asphalt);border-radius:6px;padding:.8rem 1rem;height:100%}
.rv-score .lab{color:var(--tarmac);font-size:.82rem;text-transform:uppercase;letter-spacing:.06em}
.rv-score .big{font-family:var(--display) !important;font-stretch:125%;font-variation-settings:'wdth' 125;font-weight:800;font-style:italic;font-size:2.1rem;line-height:1.1}
.rv-split{display:flex;height:10px;border-radius:5px;overflow:hidden;margin:.45rem 0 .2rem}
.rv-note{background:var(--asphalt);border-left:3px solid var(--kerb);border-radius:5px;padding:.55rem .85rem;margin:.4rem 0;font-size:.92rem}
</style>
"""


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def results():
    return rv.load_results()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def overtakes():
    return rv.load_overtakes()


def colour(team, fallback="#9A9AA8"):
    t = str(team or "").lower()
    return next((c for k, c in TEAM_COLOURS.items() if k in t), fallback)


def _team(df, code, years):
    x = df[(df["c"] == code) & (df["y"].isin(years))] if years else df[df["c"] == code]
    if x.empty:
        return None
    return x.sort_values("d")["t"].iloc[-1]


def score_card(label, a, b, sa, sb, ca, cb):
    n = sa + sb
    pa = round(100 * sa / n) if n else 50
    return (f"<div class='rv-score'><div class='lab'>{label}</div><div class='big'>{a} {sa} – {sb} {b}</div>"
            f"<div class='rv-split'><span style='width:{pa}%;background:{ca}'></span><span style='width:{100 - pa}%;background:{cb}'></span></div>"
            f"<div class='lab' style='text-transform:none;letter-spacing:0'>{a} ahead {pa}% of the time</div></div>")


def rivalry_section(focus=None):
    df = results()
    st.subheader("Rivalries: head to head")
    if df.empty:
        st.caption("Rivalry data isn't built yet. Run `python -m f1analytics rivals` once.")
        return
    years_all = sorted(int(y) for y in df["y"].unique())
    c1, c2, c3 = st.columns([1, 1, 2])
    codes = rv.drivers(df)
    st.session_state.setdefault("rv_a", focus if focus in codes else ("HAM" if "HAM" in codes else codes[0]))
    if st.session_state.get("rv_a") not in codes:
        st.session_state["rv_a"] = codes[0]
    a = c1.selectbox("Driver", codes, key="rv_a")
    others = [c for c in codes if c != a]
    default_b = "VER" if a != "VER" and "VER" in others else ("HAM" if "HAM" in others else others[0])
    if st.session_state.get("rv_b") not in others:
        st.session_state["rv_b"] = default_b
    b = c2.selectbox("Against", others, key="rv_b")
    st.session_state.setdefault("rv_years", years_all)
    years = c3.multiselect("Seasons", years_all, key="rv_years") or years_all
    ta, tb = _team(df, a, years), _team(df, b, years)
    ca, cb = colour(ta), colour(tb)
    if ca.lower() == cb.lower():
        cb = "#9A9AA8"
    r, q, s = (rv.head_to_head(df, a, b, sess, years) for sess in ("Race", "Qualifying", "Sprint"))
    if not r or not r["n"]:
        st.info(f"{a} and {b} haven't raced each other in these seasons.")
        return
    st.markdown(CSS, unsafe_allow_html=True)
    cols = st.columns(3)
    cols[0].markdown(score_card("Races", a, b, r["a"], r["b"], ca, cb), unsafe_allow_html=True)
    if q and q["n"]:
        cols[1].markdown(score_card("Qualifying", a, b, q["a"], q["b"], ca, cb), unsafe_allow_html=True)
    if s and s["n"]:
        cols[2].markdown(score_card("Sprints", a, b, s["a"], s["b"], ca, cb), unsafe_allow_html=True)
    ra, rb = rv.season_record(df, a, years), rv.season_record(df, b, years)
    facts = [f"Both on the podium together **{r['podiums']}** times."]
    if r["avg_gap"] is not None:
        lead = a if r["avg_gap"] > 0 else b
        facts.append(f"When both finish, **{lead}** is ahead by **{abs(r['avg_gap']):.1f} places** on average ({r['a_fin']}–{r['b_fin']} in those {r['both_fin']} races).")
    facts.append(f"{a}: {ra['wins']} wins, {ra['podiums']} podiums from {ra['starts']} races · {b}: {rb['wins']} wins, {rb['podiums']} podiums from {rb['starts']} races.")
    for f in facts:
        st.markdown(f"<div class='rv-note'>{_md(f)}</div>", unsafe_allow_html=True)
    seasons = rv.by_season(df, a, b, years)
    if seasons:
        rows = [{"Season": x["year"], "Races": f"{x['race'][0]}–{x['race'][1]}", "Qualifying": f"{x['qual'][0]}–{x['qual'][1]}",
                 "Sprints": f"{x['sprint'][0]}–{x['sprint'][1]}" if x["sprint"] else "–", "Both on podium": x["podiums"],
                 "Teams": "🤝 teammates at " + str(x["team_a"]) if x["teammates"] else f"{x['team_a']} vs {x['team_b']}"} for x in seasons]
        st.markdown(f"**Season by season** ({a} first)")
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    with st.expander(f"Every race: {a} vs {b}"):
        rr = pd.DataFrame(r["races"]).sort_values("date", ascending=False)
        rr[a] = rr["a"].map(lambda p: "DNF" if pd.isna(p) else f"P{int(p)}")
        rr[b] = rr["b"].map(lambda p: "DNF" if pd.isna(p) else f"P{int(p)}")
        rr["Ahead"] = [a if (pa if pd.notna(pa) else 99) < (pb if pd.notna(pb) else 99) else b for pa, pb in zip(rr["a"], rr["b"])]
        st.dataframe(rr[["year", "place", a, b, "Ahead"]].rename(columns={"year": "Season", "place": "Race"}), hide_index=True, use_container_width=True)
    gl.plain("Ahead means finishing in front, or still running when the other retired or was disqualified. Races where both retired, or either didn't start, are left out. "
             "Qualifying compares final grid order from qualifying.")
    with st.expander("The big rivalries at a glance"):
        fam = rv.famous_table(df, years)
        if fam:
            st.dataframe(pd.DataFrame([{"Rivalry": f"{x['a']} vs {x['b']}", "Races": f"{x['race'][0]}–{x['race'][1]}", "Qualifying": f"{x['qual'][0]}–{x['qual'][1]}",
                                        "Both on podium": x["podiums"], "Places apart": "–" if x["avg_gap"] is None else f"{x['avg_gap']:+.1f}"} for x in fam]),
                         hide_index=True, use_container_width=True)
            st.caption("Places apart: average finishing gap when both finish, positive when the first driver is ahead.")


def _md(text):
    import re

    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def heat_map(loc, ck, year, spots):
    if os.environ.get("F1_RIVALS_MAP", "1") == "0" or not ck:
        return False
    from f1analytics.ui.pitwall_page import _rotate, circuit_outline

    try:
        outline = circuit_outline(int(ck), int(year))
    except Exception:
        outline = None
    if not outline or not outline.get("corners"):
        return False
    share = dict(spots)
    fig = go.Figure()
    ox, oy = _rotate(outline["x"], outline["y"], outline["rotation"])
    fig.add_trace(go.Scatter(x=ox + ox[:1], y=oy + oy[:1], mode="lines", line=dict(color="#3A3A48", width=10), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=ox + ox[:1], y=oy + oy[:1], mode="lines", line=dict(color="#22222C", width=6), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=[ox[0]], y=[oy[0]], mode="markers", marker=dict(symbol="line-ns", size=16, line=dict(width=3, color="#F3F3F5")), hoverinfo="skip"))
    nums, cx, cy = zip(*outline["corners"])
    rx, ry = _rotate(list(cx), list(cy), outline["rotation"])
    top = max(share.values()) if share else 1
    sizes = [12 + 46 * (share.get(int(n), 0) / top) ** 0.8 if share.get(int(n)) else 0 for n in nums]
    alpha = [0.25 + 0.65 * share.get(int(n), 0) / top for n in nums]
    hit = [i for i, n in enumerate(nums) if share.get(int(n))]
    fig.add_trace(go.Scatter(x=[rx[i] for i in hit], y=[ry[i] for i in hit], mode="markers",
                             marker=dict(size=[sizes[i] for i in hit], color=[f"rgba(225,6,0,{alpha[i]:.2f})" for i in hit], line=dict(color="#FF8A80", width=1)),
                             customdata=[[int(nums[i]), share[int(nums[i])] * 100] for i in hit],
                             hovertemplate="Turn %{customdata[0]}: %{customdata[1]:.0f}% of passes<extra></extra>"))
    labels = [f"T{n}<br>{share[int(n)]:.0%}" if share.get(int(n), 0) >= 0.08 else f"{n}" for n in nums]
    fig.add_trace(go.Scatter(x=rx, y=ry, mode="text", text=labels, textfont=dict(size=10, color="#F3F3F5"), hoverinfo="skip"))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
    fig.update_layout(showlegend=False, height=430, margin=dict(l=4, r=4, t=4, b=4), font=FONT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, key="rv_heat", config={"displayModeBar": False})
    return True


def overtaking_section():
    races, passes = overtakes()
    st.subheader("Where can you overtake?")
    if races.empty:
        st.caption("Overtaking data isn't built yet. Run `python -m f1analytics rivals` once.")
        return
    years_all = sorted(int(y) for y in races["y"].unique())
    st.session_state.setdefault("ot_years", years_all)
    years = st.multiselect("Seasons", years_all, key="ot_years") or years_all
    table = rv.track_table(races, passes, years)
    if table.empty:
        st.caption("No passes recorded for these seasons.")
        return
    c1, c2 = st.columns([3, 2])
    with c1:
        show = pd.DataFrame({"Track": table.index, "Passes per 10 laps": table["per10"].round(1), "Races": table["races"]})
        for y in years:
            if str(y) in table:
                show[f"{y}"] = table[str(y)].map(lambda v: "–" if pd.isna(v) else int(v))
        show["Main passing spots"] = table["spots"].replace("", "–")
        st.dataframe(show, hide_index=True, use_container_width=True, height=min(38 * (len(show) + 1), 620))
        st.caption("Sorted easiest first. Each season column is that race's on-track passes.")
    with c2:
        tracks = list(table.index)
        if st.session_state.get("ot_track") not in tracks:
            mappable = [t for t in tracks if rv.located_share(passes, t, years)[0] >= rv.MIN_PLACED]
            st.session_state["ot_track"] = mappable[0] if mappable else tracks[0]
        loc = st.selectbox("Track", tracks, key="ot_track")
        spots = rv.corners(passes, loc, years)
        rr = races[(races["loc"] == loc) & races["y"].isin(years)]
        ck = rr["ck"].dropna().iloc[-1] if "ck" in rr and rr["ck"].notna().any() else None
        year = int(rr["y"].max()) if len(rr) else years_all[-1]
        done, total = rv.located_share(passes, loc, years)
        if done < rv.MIN_PLACED:
            spots = []
        if spots and not heat_map(loc, ck, year, spots):
            fig = go.Figure(go.Bar(x=[f"T{c}" for c, _ in spots[:8]], y=[s * 100 for _, s in spots[:8]], marker_color="#E10600"))
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), font=FONT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            fig.update_yaxes(title_text="% of passes", gridcolor="#2E2E3A")
            st.plotly_chart(fig, key="rv_heat_bar", config={"displayModeBar": False})
        if spots:
            st.caption(f"Bigger, brighter circle = more passes at that corner. {done} of {total} passes could be placed on the lap.")
        else:
            st.caption(f"Only {done} of {total} passes could be placed on the lap here, too few to map." if total else "No passes to map here.")
    change = rv.year_change(races)
    if change and 2025 in years and 2026 in years:
        pct = (change["after"] / change["before"] - 1) * 100 if change["before"] else 0
        big = ", ".join(f"{l} {b0} → {b1}" for l, b0, b1 in change["biggest"])
        st.markdown(f"<div class='rv-note'>2026 rules: on the {change['tracks']} tracks raced in both 2025 and 2026, passes went from "
                    f"<b>{change['before']}</b> to <b>{change['after']}</b> ({pct:+.0f}%), up at {change['up']} of {change['tracks']}. Biggest jumps: {big}.</div>",
                    unsafe_allow_html=True)
    gl.plain("Only real racing passes count: lap 1, Safety Car and red-flag periods, places changed in the pits and lapping backmarkers are all removed. "
             "Passes per 10 laps uses green-flag laps, so a race full of Safety Cars isn't punished. The corner is approximate: it's placed from a reference GPS lap and the moment the timing shows the position change. "
             "2023 is left out because its overtaking data isn't reliable.")


STORIES_AS_OF = "3 November 2026, after the Mexico City GP"
STORIES = [
    ("Mercedes' engine loophole",
     "The 2026 rules cap the engine's compression ratio (how hard fuel and air are squeezed before they burn) at 16:1, but it was only measured with the engine cold. "
     "Ferrari, Audi and Honda suspected Mercedes' engine went above that once hot. The FIA changed the test: from 1 June 2026 it is checked cold and hot, and from 2027 only at running temperature.",
     "Mercedes has been the team to beat all year, and Antonelli won the title in their car, so rivals still argue the early-season edge mattered.",
     "Crash.net", "https://www.crash.net/f1/news/1090578/1/fia-makes-final-ruling-mercedes-f1-engine-controversy"),
    ("'Battery world championship'",
     "Half the power now comes from the battery, and drivers spend the lap deciding where to spend and recharge it: super clipping on straights, slower lines through fast corners, lifting before braking. "
     "Verstappen called it \"playing Mario Kart\" and \"not racing\" after China; Alonso and others complained too.",
     "The FIA changed the energy rules from Miami (3 May): shorter, stronger super-clip bursts in qualifying and full electric power only in the main acceleration zones.",
     "Motor Sport", "https://www.motorsportmagazine.com/articles/single-seaters/f1/understanding-verstappens-gripes-with-f1s-battery-world-championship/"),
    ("Yo-yo overtaking",
     "Overtake mode gives the car behind extra battery power, so passes are easier, but the passer can be left empty on the next straight and get passed straight back. "
     "Isack Hadjar said one pass can cost \"five laps recovering energy\".",
     "Passes are up about 45% on tracks raced in both 2025 and 2026, but critics say many of them are battery swaps, not racing. See the overtaking table above.",
     "The Race", "https://www.the-race.com/formula-1/six-weirdest-things-about-f1-2026-cars-explained/"),
    ("Starts and turbo lag",
     "With no MGU-H to spin the turbo, cars sit on the grid at high revs for a long time and some get away very slowly, a danger with cars behind at full speed.",
     "From Miami the FIA added a 'low-power start' safety system that deploys battery power automatically if a car is crawling off the line.",
     "Motor Sport", "https://www.motorsportmagazine.com/articles/single-seaters/f1/2026-f1-mid-season-rules-changes-whats-been-agreed-and-why/"),
    ("Aston Martin-Honda's flop",
     "Newey's first car, Honda's new works engine and Alonso were meant to make Aston Martin winners. Instead they had one point after 11 races.",
     "The most-named disappointment of the year in The Race's mid-season verdict.",
     "The Race", "https://www.the-race.com/formula-1/our-verdict-on-f1-2026s-biggest-disappointments-so-far/"),
    ("Mexico: Ferrari vs Ferrari",
     "Hamilton took his first Ferrari pole. At Turn 4 on lap 1 Leclerc passed him off the track, Verstappen got through, and Leclerc got 5 seconds for leaving the track and gaining an advantage. "
     "Hamilton said he was \"pushed out by my own teammate\". The penalty put Leclerc behind Verstappen at the stops, a red flag after Bottas's crash froze that order, and Verstappen won with Hamilton 0.8 s behind.",
     "Antonelli's third place made him the youngest champion ever, at 20. Lawson was also thrown out of qualifying for breaking the battery-power rules. See the Race review in Past races for the full breakdown.",
     "PlanetF1", "https://www.planetf1.com/news/mexican-grand-prix-2026-race-report"),
]


def storylines_section(year=2026):
    df = results()
    st.subheader(f"{year} storylines")
    st.caption(f"Rookies table updates with every race. Controversy notes as of {STORIES_AS_OF}.")
    if not df.empty and year in set(df["y"]):
        st.markdown("**Young drivers to watch**")
        rows = []
        for x in rv.young_drivers(df, year):
            rows.append({"Driver": x["code"], "Where he is": f"{x['label']} · {x['team']}", "Races": x["starts"], "Wins": x["wins"], "Podiums": x["podiums"],
                         "Best finish": "–" if x["best"] is None else f"P{x['best']}", "Top-10 finishes": x["top10"],
                         "Vs teammate (races)": f"{x['race'][0]}–{x['race'][1]} vs {x['mate']}" if x["race"] else "–",
                         "Vs teammate (qualifying)": f"{x['qual'][0]}–{x['qual'][1]}" if x["qual"] else "–", "DNFs": x["dnfs"]})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        gl.plain("The teammate is whoever drove the other car in the same team most often this season. A retirement counts as finishing behind.")
    st.markdown("**The controversies, explained**")
    for title, what, why, src, url in STORIES:
        with st.expander(title):
            st.markdown(f"{what}\n\n**Why it matters:** {why}\n\nSource: [{src}]({url})")


def page(focus=None):
    st.markdown(CSS, unsafe_allow_html=True)
    rivalry_section(focus)
    st.divider()
    overtaking_section()
    st.divider()
    storylines_section()
    gl.words("rivals", "Rivalry and overtaking words explained")
