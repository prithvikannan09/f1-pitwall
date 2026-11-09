import html
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from f1analytics.ui.season_pages import CSS

DATA = Path(__file__).resolve().parent.parent / "styles" / "season_extras_2026.json"
FONT = dict(family="Michroma, sans-serif", color="#F3F3F5", size=11)
RULES = """
**How upgrades are declared (FIA rules)**
- Before every Grand Prix, each team must tell the FIA which parts of the car are new and why (more downforce, less drag, cooling, reliability…). The FIA publishes these as **Car Presentation Submissions**, so everyone can see who brought what.
- A "part" is one item on that list, such as a new front wing or a changed floor edge. A big package can be one line or ten, so counts show how busy a team is, not how much faster it got.
- Every upgrade has to be paid for inside the **budget cap** (about $215m in 2026). Crash repairs come out of the same budget, which is why a big crash bill can slow a team's upgrades.
- 2026 brought all-new car rules (smaller, lighter cars with active aerodynamics), so teams are bringing more new parts than usual.
"""


def load():
    return json.loads(DATA.read_text())


def _team_colour(team, grid):
    t = team.lower().split()[0]
    for v in grid.values():
        name = str(v.get("team") or "").lower()
        if name.startswith(t) or (t == "racing" and "racing bulls" in name):
            if t == "red" and "racing bulls" in name:
                continue
            return v["colour"]
    return "#9A9AA8"


def _grid():
    try:
        from f1analytics.ui.pitwall_page import _grid as g

        return g()
    except Exception:
        return {}


def _chart(fig, h):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=30, b=10), font=FONT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      showlegend=False)
    fig.update_xaxes(gridcolor="#2E2E3A")
    fig.update_yaxes(gridcolor="#2E2E3A")
    return fig


def upgrade_totals(d):
    tot = {t: 0 for t in d["upgrades"]["teams"]}
    for r in d["upgrades"]["rounds"]:
        for t, c in r["counts"].items():
            tot[t] = tot.get(t, 0) + c
    return pd.Series(tot).sort_values(ascending=False)


def destructors_teams(d):
    df = pd.DataFrame(d["destructors"]["drivers"])
    return df.groupby("team")["usd"].sum().sort_values(ascending=False), df.sort_values("usd", ascending=False)


def upgrades_page():
    st.markdown(CSS, unsafe_allow_html=True)
    d = load()
    grid = _grid()
    tot = upgrade_totals(d)
    st.markdown(f"<div class='hc hc-tab'><div class='hc-k'>2026 car upgrades declared to the FIA · {html.escape(d['as_of'])}</div>"
                f"<div class='hc-big'>{int(tot.sum())} new parts so far</div><div class='hc-sub'>Most: {html.escape(tot.index[0])} ({int(tot.iloc[0])}). "
                f"Fewest: {html.escape(tot.index[-1])} ({int(tot.iloc[-1])}).</div></div>", unsafe_allow_html=True)
    fig = go.Figure(go.Bar(x=tot.values[::-1], y=tot.index[::-1], orientation="h", text=tot.values[::-1], textposition="outside",
                           marker_color=[_team_colour(t, grid) for t in tot.index[::-1]]))
    fig.update_layout(xaxis_title="New parts declared", xaxis_range=[0, tot.max() * 1.12])
    st.plotly_chart(_chart(fig, 420), use_container_width=True, config={"displayModeBar": False})
    rounds = d["upgrades"]["rounds"]
    head = "".join(f"<th>{html.escape(r['label'])}{' *' if 'approx' in r['src'] or 'reported' in r['src'] else ''}</th>" for r in rounds)
    body = ""
    for t in tot.index:
        cells = "".join(f"<td class='{'up-0' if not r['counts'].get(t) else ''}'>{r['counts'].get(t, 0)}</td>" for r in rounds)
        body += f"<tr><td><i class='st-bar' style='background:{_team_colour(t, grid)}'></i>{html.escape(t)}</td>{cells}<td class='st-n'><b>{int(tot[t])}</b></td></tr>"
    st.markdown(f"<div class='hc hc-tab' style='overflow-x:auto'><div class='hc-h'>Race by race</div><table class='st up'><tr><th>Team</th>{head}<th>Total</th></tr>{body}</table></div>",
                unsafe_allow_html=True)
    st.caption("* Monza: counted from RACER's write-up of the upgrades (approximate). Sepang: reported upgrades, not checked against the FIA list.")
    with st.expander("How upgrades work under the FIA rules"):
        st.markdown(RULES)
    src = d["upgrade_sources"]
    st.caption("Sources: " + " · ".join(f"[{t}]({u})" for t, u in src.values()))


def destructors_page():
    st.markdown(CSS, unsafe_allow_html=True)
    d = load()
    grid = _grid()
    teams, drivers = destructors_teams(d)
    total = teams.sum()
    fer = list(teams.index).index("Ferrari") + 1 if "Ferrari" in teams.index else None
    st.markdown(f"<div class='hc hc-tab'><div class='hc-k'>2026 Destructors' Championship · crash damage costs · {html.escape(d['as_of'])}</div>"
                f"<div class='hc-big'>${total / 1e6:.2f}m of damage so far</div>"
                f"<div class='hc-sub'>Leading: {html.escape(teams.index[0])} (${teams.iloc[0] / 1e6:.2f}m). Worst driver: {html.escape(drivers.iloc[0]['driver'])} "
                f"(${drivers.iloc[0]['usd'] / 1e6:.2f}m). Ferrari are P{fer} on ${teams['Ferrari'] / 1e6:.2f}m, with Leclerc P3 among drivers.</div></div>",
                unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure(go.Bar(x=(teams.values / 1e6)[::-1], y=teams.index[::-1], orientation="h",
                               text=[f"${v / 1e6:.2f}m" for v in teams.values[::-1]], textposition="outside",
                               marker_color=[_team_colour(t, grid) for t in teams.index[::-1]]))
        fig.update_layout(title="Teams (sum of their drivers)", xaxis_title="US$ million", xaxis_range=[0, teams.max() / 1e6 * 1.3])
        st.plotly_chart(_chart(fig, 440), use_container_width=True, config={"displayModeBar": False})
    with c2:
        rows = "".join(f"<tr><td>{i}</td><td><i class='st-bar' style='background:{_team_colour(r['team'], grid)}'></i>{html.escape(r['driver'])}"
                       f"<span class='hc-dim'> {html.escape(r['team'])}</span></td><td class='st-n'>${r['usd']:,.0f}</td></tr>"
                       for i, (_, r) in enumerate(drivers.iterrows(), 1))
        st.markdown(f"<div class='hc hc-tab' style='max-height:460px;overflow-y:auto'><div class='hc-h'>Drivers</div>"
                    f"<table class='st'><tr><th>Pos</th><th>Driver</th><th>Damage</th></tr>{rows}</table></div>", unsafe_allow_html=True)
    note = f"{d['destructors']['method']} ₹ guide: US${total / 1e6:.1f}m ≈ ₹{total * 88 / 1e7:.0f} crore at ₹88 to the dollar (assumed rate)."
    st.caption(note.replace("$", "\\$") + " Sources: " + " · ".join(f"[{t}]({u})" for t, u in d["destructors"]["sources"]))


def home_cards():
    try:
        d = load()
    except Exception:
        return "", ""
    tot = upgrade_totals(d)
    teams, drivers = destructors_teams(d)
    up = (f"<div class='hc'><div class='hc-k'>2026 tech upgrades</div><div class='hc-big hc-mid'>{int(tot.sum())} new parts</div>"
          f"<div class='hc-sub'>Most: {html.escape(tot.index[0])} ({int(tot.iloc[0])}) · Ferrari {int(tot.get('Ferrari', 0))}</div>"
          f"<div class='hc-sub'>Declared to the FIA before each race.</div></div>")
    de = (f"<div class='hc'><div class='hc-k'>Destructors' Championship</div><div class='hc-big hc-mid'>${teams.sum() / 1e6:.2f}m in crash damage</div>"
          f"<div class='hc-sub'>Leading: {html.escape(teams.index[0])} · Worst driver: {html.escape(drivers.iloc[0]['driver'])}</div>"
          f"<div class='hc-sub'>Estimates, not official.</div></div>")
    return up, de
