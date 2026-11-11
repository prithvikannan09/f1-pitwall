import html
import textwrap

import streamlit as st

RACE_CODE = {
    "Melbourne": "AUS", "Shanghai": "CHN", "Suzuka": "JPN", "Sakhir": "BHR", "Jeddah": "SAU", "Miami Gardens": "MIA", "Miami": "MIA",
    "Montréal": "CAN", "Montreal": "CAN", "Monte Carlo": "MON", "Monaco": "MON", "Barcelona": "BAR", "Spielberg": "AUT", "Silverstone": "GBR",
    "Spa-Francorchamps": "BEL", "Budapest": "HUN", "Zandvoort": "NED", "Monza": "ITA", "Madrid": "MAD", "Baku": "AZE", "Kuala Lumpur": "SEP",
    "Marina Bay": "SIN", "Singapore": "SIN", "Austin": "USA", "Mexico City": "MEX", "São Paulo": "SAO", "Sao Paulo": "SAO", "Las Vegas": "LVG",
    "Lusail": "QAT", "Yas Marina": "ABU", "Yas Island": "ABU",
    "China": "CHN", "Japan": "JPN", "Canada": "CAN", "Austria": "AUT", "Britain": "GBR", "Belgium": "BEL", "Hungary": "HUN",
    "Netherlands": "NED", "Italy": "ITA", "Australia": "AUS", "Bahrain": "BHR", "Azerbaijan": "AZE",
}

TABS = [("Home", "home", "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z", ("Home",)),
        ("Live", "live", "M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14", ("Live",)),
        ("Races", "replay", "M5 21V4M5 4h11l-2 4 2 4H5", ("Past races", "Rivals & tracks")),
        ("Perform", "performance", "M3 20h18M6 16l4-5 3 3 5-7", ("Performance",)),
        ("More", "more", "M4 7h16M4 12h16M4 17h16", ("More", "Schedule", "Results", "Standings", "Upgrades", "Destructors"))]

MORE = [("Season", [("Schedule", "schedule", "Every race and session"), ("Results", "results", "Race by race"), ("Standings", "standings", "Drivers and teams")]),
        ("Races", [("Past races", "replay", "Replays and race review"), ("Rivals & tracks", "rivals", "Head to head over the season")]),
        ("Cars", [("Upgrades", "upgrades", "Parts, engines, did they work?"), ("Destructors", "destructors", "Crash damage costs")])]

CSS = """<style>
.pw-tabbar{display:none}
.pw-how summary p{font-size:.72rem !important;opacity:.75}
@media (max-width:640px){
  html,body,.stApp{font-size:14px}
  .block-container{padding:2.8rem .9rem 6.2rem !important}
  .stApp h1{font-size:1.05rem !important;letter-spacing:.12em;line-height:1.3 !important}
  [data-testid="stColumn"]:has(.pw-signin-mark){display:none !important}
  .stApp h2{font-size:1rem !important}
  .stApp h3{font-size:.95rem !important}
  .stApp h4{font-size:.86rem !important;margin:.9rem 0 .4rem !important;line-height:1.4 !important}
  .stApp h5{font-size:.78rem !important;line-height:1.4 !important}
  .stApp p,.stApp li{font-size:.8rem;line-height:1.65}
  [data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{font-size:.68rem !important;line-height:1.6 !important}
  [data-testid="stColumn"]:has(.pw-nav-mark){display:none !important}
  [data-testid="stHorizontalBlock"]:has(.pw-nav-mark){gap:.4rem !important}
  .pw-tabbar{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));position:fixed;left:0;right:0;bottom:0;height:64px;z-index:999990;
    background:#14141C;border-top:1px solid #2E2E3A;padding-bottom:env(safe-area-inset-bottom)}
  .pw-tabbar a{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;font-size:.6rem;color:#A3A3B2 !important;text-decoration:none !important;letter-spacing:.04em}
  .pw-tabbar a.on{color:#F3F3F5 !important}
  .pw-tabbar a.on svg{stroke:#E10600}
  [data-testid="stTabs"] [role="tablist"]{gap:1.1rem;overflow-x:auto;flex-wrap:nowrap;scrollbar-width:none}
  [data-testid="stTabs"] [role="tab"]{padding:.55rem 0 !important;min-height:40px;white-space:nowrap}
  [data-testid="stTabs"] [role="tab"] p{font-size:.66rem !important;letter-spacing:.04em}
  [data-testid="stRadio"] [role="radiogroup"]{gap:.3rem !important;flex-wrap:wrap}
  [data-testid="stRadio"] [role="radiogroup"] label{margin:0 !important;padding:.45rem .75rem !important;border:1px solid #2E2E3A;border-radius:999px;background:#1A1A24;min-height:36px}
  [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked){background:#2E2E3A;border-color:#55556A}
  [data-testid="stRadio"] [role="radiogroup"] label>div:first-child{display:none}
  [data-testid="stRadio"] [role="radiogroup"] label p{font-size:.66rem !important}
  [data-testid="stWidgetLabel"] p{font-size:.66rem !important;letter-spacing:.06em;opacity:.8}
  [data-baseweb="select"]>div{min-height:44px;border-radius:12px !important}
  [data-testid="stExpander"] summary{min-height:44px}
  [data-testid="stExpander"] details{border-radius:14px !important}
  .hc,.duel-card,.upc,.ck,.pw-empty{border-radius:14px !important;padding:.85rem .9rem !important}
  .hc-big{font-size:1.15rem !important;line-height:1.35 !important}
  .hc-k,.duel-k{font-size:.6rem !important;letter-spacing:.1em}
  .hc-sub,.duel-dim{font-size:.66rem !important;line-height:1.55}
  .duel-v{font-size:1rem !important}
  .duel-head{font-size:.78rem !important;line-height:1.6 !important}
  .duel-list li{font-size:.72rem !important;line-height:1.6 !important}
  table.duel-t,table.st{font-size:.66rem !important;display:block;overflow-x:auto;white-space:nowrap}
  .upc-grid{grid-template-columns:1fr !important}
  .upc ul{font-size:.68rem !important}
  [data-testid="stPlotlyChart"]{margin:0 -.3rem}
  [data-testid="stSidebarCollapsedControl"]{top:.55rem}
}
</style>"""


def styles():
    st.markdown(CSS, unsafe_allow_html=True)


def tabbar(view):
    q = st.query_params
    keep = "".join(f"&{k}={html.escape(str(q.get(k)))}" for k in ("team", "driver") if q.get(k))
    links = ""
    for label, mode, icon, views in TABS:
        on = " on" if view in views else ""
        links += (f"<a class='pw-tab{on}' href='?mode={mode}{keep}' target='_self' aria-label='{label}'>"
                  f"<svg width='22' height='22' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' "
                  f"stroke-linejoin='round' aria-hidden='true'><path d='{icon}'></path></svg>{label}</a>")
    st.markdown(f"<nav class='pw-tabbar' aria-label='Main'>{links}</nav>", unsafe_allow_html=True)


def more_page():
    q = st.query_params
    keep = "".join(f"&{k}={html.escape(str(q.get(k)))}" for k in ("team", "driver") if q.get(k))
    out = ""
    for title, items in MORE:
        rows = "".join(f"<a class='mo-row' href='?mode={m}{keep}' target='_self'><span><b>{html.escape(n)}</b><i>{html.escape(d)}</i></span><em>›</em></a>"
                       for n, m, d in items)
        out += f"<div class='mo-k'>{html.escape(title.upper())}</div><div class='mo-card'>{rows}</div>"
    st.markdown("""<style>
.mo-k{font-size:.6rem;letter-spacing:.12em;opacity:.7;margin:1rem 0 .4rem .2rem}
.mo-card{background:#1A1A24;border:1px solid #2E2E3A;border-radius:16px;overflow:hidden}
.mo-row{display:flex;align-items:center;justify-content:space-between;min-height:56px;padding:.4rem 1rem;color:#F3F3F5 !important;text-decoration:none !important}
.mo-row+.mo-row{border-top:1px solid #2E2E3A}
.mo-row b{display:block;font-size:.8rem;font-weight:400}
.mo-row i{display:block;font-style:normal;font-size:.62rem;color:#A3A3B2;margin-top:.25rem}
.mo-row em{font-style:normal;color:#A3A3B2}
</style>""" + out, unsafe_allow_html=True)
    st.markdown("<div class='mo-k'>YOU</div>", unsafe_allow_html=True)
    try:
        from f1analytics.ui.pitwall_page import owner_signin

        owner_signin()
    except Exception:
        pass
    st.caption("Settings (pit-stop override, refresh rate, beginner mode) are in the side menu: tap › at the top left.")


def how(text, label="How it's worked out"):
    with st.expander(label):
        st.markdown(f"<div class='pw-how-body' style='font-size:.72rem;line-height:1.65;opacity:.85'>{text}</div>", unsafe_allow_html=True)


def wrap_title(text, width=40):
    if not text:
        return text, 0
    lines = textwrap.wrap(str(text), width) or [str(text)]
    return "<br>".join(lines), len(lines)


def tidy(fig):
    t = fig.layout.title.text if fig.layout.title and fig.layout.title.text else None
    shown = any(getattr(tr, "showlegend", None) is not False and getattr(tr, "name", None) for tr in fig.data) and fig.layout.showlegend is not False
    top = 16
    if t:
        wrapped, n = wrap_title(t)
        fig.update_layout(title=dict(text=wrapped, x=0, xanchor="left", y=1, yanchor="top", pad=dict(t=6), font=dict(size=12)))
        top += 17 * n + 8
    if shown:
        fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, font=dict(size=10)))
        top += 26
    m = fig.layout.margin
    fig.update_layout(margin=dict(l=m.l if m.l is not None else 10, r=m.r if m.r is not None else 10, b=m.b if m.b is not None else 10, t=top))
    return fig


def code(location):
    return RACE_CODE.get(str(location), str(location)[:3].upper())


def install_chart_tidy():
    if getattr(st.plotly_chart, "_pw_tidy", False):
        return
    orig = st.plotly_chart

    def plotly_chart(fig, *a, **k):
        try:
            fig = tidy(fig)
        except Exception:
            pass
        return orig(fig, *a, **k)

    plotly_chart._pw_tidy = True
    st.plotly_chart = plotly_chart
