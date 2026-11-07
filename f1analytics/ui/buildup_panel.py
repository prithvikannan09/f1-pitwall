import html

import pandas as pd
import streamlit as st

from f1analytics.pitwall import preview as pv

TOP_N = 8
NOTES = pv.OLD_RESULTS_FILE.parent / "weekend_notes.json"


def weekend_notes(location):
    import json

    try:
        n = json.loads(NOTES.read_text())
    except (OSError, ValueError):
        return None
    loc = str(location or "").lower()
    return n if n.get("meeting", "").lower() in loc or loc in n.get("meeting", "").lower() else None


def notes_card(n, focus=None):
    if not n:
        return
    pen = "".join(f"<div class='bu-pen{' bu-me' if p['code'] == focus else ''}'><b>{html.escape(p['code'])}</b>"
                  f"<span class='bu-drop'>{html.escape(p['drop'])}</span><div class='bu-t'>{html.escape(p['reason'])}</div></div>"
                  for p in n.get("penalties", []))
    inc = "".join(f"<div class='bu-l'>⚠️ <b>{html.escape(i['code'])} · {html.escape(i['session'])}:</b> {html.escape(i['text'])}</div>"
                  for i in n.get("incidents", []))
    src = " · ".join(f"<a href='{html.escape(u)}' target='_blank'>{html.escape(t)}</a>" for t, u in n.get("sources", []))
    st.markdown(f"<div class='bu-card bu-notes'><div class='ck-h'>Grid penalties and car issues</div>"
                f"<div class='bu-pens'>{pen}</div>{inc}"
                f"<div class='bu-t' style='margin-top:.5rem'>{html.escape(n.get('status_note', ''))} Updated {html.escape(n.get('as_of', ''))}. "
                f"Sources: {src}</div></div>", unsafe_allow_html=True)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _build(location, stamp):
    return pv.build(location)


def _stamp():
    p = pv.OLD_RESULTS_FILE.parent / "racecraft_2026.json"
    return p.stat().st_mtime if p.exists() else 0


def _track_line(rec):
    if not rec or not rec.get("finishes"):
        return "First time here"
    last = list(zip(rec["years"], rec["finishes"]))[-4:]
    s = " ".join(f"’{str(y)[2:]} {'DNF' if f is None else f'P{f}'}" for y, f in last)
    return s + (f" · {rec['wins']} win{'s' if rec['wins'] != 1 else ''}" if rec.get("wins") else "")


def _range(r):
    lo, hi = sorted((int(r["rank_low"]), int(r["rank_high"])))
    return f"P{int(r['rank_base'])}" + (f" <span class='bu-r'>(P{lo}–P{hi})</span>" if lo != hi else "")


def buildup_section(location, focus=None, race_kind=None, title=True):
    if not location:
        return
    b = _build(location, _stamp())
    if not b or b["ranked"].empty:
        return
    ranked, table, lap_s = b["ranked"], b["table"], b["lap_s"]
    if title:
        st.subheader(f"Weekend build-up · {location}")
    st.caption(f"Pace from {b['races']} races of 2026 telemetry (latest: {b['last']}), recent results, and every race here since 2016. "
               "Recent races and recent years count more. These are estimates, not predictions of the result.")
    if race_kind == "rain":
        st.markdown("<div class='bu-wet'>🌧️ <b>Rain is forecast for the race.</b> All of this pace data is from dry running, so it counts for less: "
                    "wet-weather skill, tyre warm-up and luck with Safety Cars matter more on a wet Sunday.</div>", unsafe_allow_html=True)
    notes = weekend_notes(location)
    notes_card(notes, focus)
    drops = {p["code"]: p["drop"] for p in (notes or {}).get("penalties", [])}
    rows = []
    for code, r in ranked.head(TOP_N).iterrows():
        pace = r.get("pace_pct_last")
        pace_s = "—" if pace is None or pd.isna(pace) else f"{pace:.2f}% · {pace / 100 * lap_s:.2f}s"
        wear = r.get("wear_rel_last")
        wear_s = "—" if wear is None or pd.isna(wear) else ("level" if abs(wear) < 0.0005 else f"{wear:+.3f}s")
        me = " bu-me" if code == focus else ""
        rows.append(f"<tr class='bu-row{me}'><td class='bu-p'>{_range(r)}</td><td><b>{html.escape(code)}</b>"
                    f"<div class='bu-t'>{html.escape(str(b['teams'].get(code) or ''))}</div>"
                    f"{'<div class=bu-tag>Grid: ' + html.escape(drops[code]) + '</div>' if code in drops else ''}</td>"
                    f"<td>{pace_s}</td><td>P{r['form']:.1f}</td><td>{wear_s}</td><td class='bu-h'>{_track_line(r['track'])}</td></tr>")
    st.markdown("<div class='bu-wrap'><table class='bu'><thead><tr><th>Pick</th><th>Driver</th><th>Pace, last 5</th><th>Form</th>"
                "<th>Tyre wear</th><th>Here before</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>",
                unsafe_allow_html=True)
    st.caption("Pick: base ranking, with the range across the low and high weightings. Pace: % off the best car on clean laps, and seconds a lap here. "
               "Form: average finish this season, recent races weighted more (DNF counts as P18). Tyre wear: seconds lost per lap against the field (minus is easier on tyres).")

    if focus and focus in table.index:
        lines = pv.insights(focus, table, ranked, lap_s)
        if lines:
            pick = f" · tipped P{int(ranked.loc[focus, 'rank_base'])}" if focus in ranked.index else ""
            st.markdown(f"<div class='bu-card'><div class='ck-h'>{html.escape(focus)} this weekend{pick}</div>"
                        + "".join(f"<div class='bu-l'>{html.escape(x)}</div>" for x in lines) + "</div>", unsafe_allow_html=True)

    easy, hard = pv.tyre_board(table.loc[table.index.intersection(ranked.index)])
    if easy:
        def cells(items):
            return "".join(f"<div class='bu-tw'><b>{c}</b> {v:+.3f}s/lap <span>≈ {abs(cost):.1f}s {'gained' if cost < 0 else 'lost'} over {pv.STINT_LAPS} laps</span></div>"
                           for c, v, cost in items)
        st.markdown(f"<div class='bu-tyres'><div><div class='pw-k'>Easiest on tyres</div>{cells(easy)}</div>"
                    f"<div><div class='pw-k'>Hardest on tyres</div>{cells(hard)}</div></div>", unsafe_allow_html=True)

    with st.expander("How the build-up is worked out"):
        st.markdown(
            f"""
- **Pace** = median % off the fastest car on clean laps (no traffic, pits or Safety Car), fuel-corrected. Each race is weighted **0.5^(races ago ÷ 3)**, so the last race counts double the one three races back.
- **Form** = average finishing place this season with the same recency weights. DNF counts as P18.
- **Track history** = average finish here since 2016, weighted **0.5^(years ago ÷ 3)** and pulled towards P10 by one imaginary average race, so one lucky result doesn't dominate.
- Each is turned into a z-score (how far above or below the grid average) and combined:
  - **Base** = 0.5 × pace + 0.3 × form + 0.2 × track
  - **Low** (pace-heavy) = 0.6 / 0.3 / 0.1
  - **High** (history-heavy) = 0.4 / 0.25 / 0.35
- **Tyre wear** = how much faster a driver's lap times drop off than the field's on the same tyre, in seconds per lap. Over a {pv.STINT_LAPS}-lap stint that adds up as wear × laps × (laps − 1) ÷ 2.
- Only drivers with at least 3 races of 2026 data are ranked. Telemetry: OpenF1. Old results: Jolpica (Ergast).
"""
        )
