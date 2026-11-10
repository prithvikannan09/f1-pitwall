import html

import plotly.graph_objects as go
import streamlit as st

from f1analytics.pitwall import duel, whatif
from f1analytics.ui.duel_panel import CSS, _chart


def _pos(raw, num):
    res = raw.get("session_result")
    try:
        row = res[res["driver_number"] == num]
        return int(row["position"].iloc[0])
    except Exception:
        return None


def _card(col, k, v, sub, colr="#9A9AA8"):
    col.markdown(f"<div class='duel-card' style='border-left-color:{colr}'><div class='duel-k'>{k}</div><div class='duel-v'>{v}</div>"
                 f"<div class='duel-dim' style='font-size:.68rem'>{sub}</div></div>", unsafe_allow_html=True)


def _chart_delta(r, cls, code, colr):
    lap, n, cost, g = r["lap"], r["laps"], r["cost"], r["gain"]
    xs = [lap - 1, lap + 1] + list(range(lap + 2, lap + n + 1))
    fig = go.Figure()

    def line(gain):
        return [0, -cost] + [-cost + gain * (x - lap - 1) for x in xs[2:]]

    fig.add_trace(go.Scatter(x=xs, y=line(g["high"]), mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=xs, y=line(g["low"]), mode="lines", line=dict(width=0), fill="tonexty", fillcolor="rgba(255,255,255,.12)",
                             name="Low to high estimate", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=xs, y=line(g["base"]), mode="lines", line=dict(color=colr, width=2.5), name="Best estimate",
                             hovertemplate="Lap %{x}: %{y:+.1f}s vs the real race<extra></extra>"))
    fig.add_hline(y=0, line_color="#55556A", line_dash="dot", annotation_text="the real race", annotation_font_size=9)
    for d, gap in cls["ahead"][:4]:
        if gap < cost * 2 + 5:
            fig.add_hline(y=-gap, line_color="#77778A", line_width=1, annotation_text=f"{code.get(d, d)} at the flag", annotation_font_size=9,
                          annotation_position="bottom left")
    fig.update_layout(title="Race time compared with what really happened", xaxis_title="Lap", yaxis_title="Seconds (below zero = ahead of the real race)")
    return _chart(fig, 340)


def whatif_tab(raw, laps, sk, code, colour, present, focus):
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("#### What if they had skipped a pit stop?")
    key = f"wi_drv_{sk}"
    if st.session_state.get(key) not in present:
        st.session_state[key] = focus
    c1, c2 = st.columns(2)
    num = c1.selectbox("Driver", present, format_func=code.get, key=key)
    who, colr = code.get(num, str(num)), colour.get(num, "#E10600")
    stops = whatif.skippable_stops(raw, num)
    if not stops:
        st.caption(f"{who} has no stop that could be skipped: every stop was a forced change between wet and dry tyres, or the only one.")
        move_section(raw, laps, sk, code, num, who, colr)
        return

    def label(i):
        s = stops[i]
        return f"Lap {s['lap']}: {s['old']['compound'].title()} to {s['new']['compound'].title()}"

    i = c2.selectbox("Stop to skip", range(len(stops)), format_func=label, key=f"wi_stop_{sk}_{num}")
    stop = stops[i]
    r = whatif.skip_stop(raw, laps, num, stop)
    if r is None:
        st.caption("Not enough clean laps around this stop to run the numbers.")
        move_section(raw, laps, sk, code, num, who, colr)
        return
    g, net = r["gain"], r["net"]
    cls = {k: whatif.reclassify(laps, num, net[k]) for k in ("low", "base", "high")}
    pos = _pos(raw, num)
    tyre = r["compound"].title()

    def finish(k):
        p = cls[k]["places"]
        return f"P{pos - p}" if pos else f"{p:+d} places"

    m = st.columns(4)
    _card(m[0], "Stop cost", f"{r['cost']:.1f}s", "Slow lap into the pits plus slow lap out, against normal laps.", colr)
    _card(m[1], "New tyres won back", f"{g['base'] * r['laps']:.1f}s", f"{g['base']:.2f}s a lap over {r['laps']} laps "
          f"(range {g['low']:.2f} to {g['high']:.2f}).", duel.COMPOUND_COLOUR.get(r["compound"], "#9A9AA8"))
    better = net["base"] > 0
    _card(m[2], "Staying out", f"{abs(net['base']):.1f}s {'faster' if better else 'slower'}", f"Range {net['low']:+.1f}s to {net['high']:+.1f}s (plus = faster).",
          "#43B02A" if better else "#E10600")
    rng = finish("low") if finish("low") == finish("high") else f"{finish('low')} to {finish('high')}"
    _card(m[3], "Finish", f"{'P' + str(pos) + ' → ' if pos else ''}{finish('base')}", f"Range: {rng}.", "#43B02A" if cls["base"]["places"] > 0 else "#9A9AA8")
    names = [f"{code.get(d, d)} (by {t:.1f}s)" for d, t in cls["base"]["passed"]]
    nxt = [(d, gap) for d, gap in cls["base"]["ahead"] if d not in {x for x, _ in cls["base"]["passed"]}]
    if cls["base"]["places"] > 0:
        verdict = f"On the numbers, skipping the lap {r['lap']} stop puts {who} ahead of {', '.join(names)} at the flag."
    elif better:
        verdict = f"Skipping the lap {r['lap']} stop saves time but not enough to gain a place."
    else:
        verdict = "The stop was the right call: new tyres won back more than the stop cost."
    if better and nxt:
        d, gap = nxt[0]
        verdict += f" The next car, {code.get(d, d)}, would still be {gap - net['base']:.1f}s up the road."
    st.markdown(f"<div class='duel-head'>{html.escape(verdict)}</div>", unsafe_allow_html=True)
    st.plotly_chart(_chart_delta(r, cls["base"], code, colr), use_container_width=True, config={"displayModeBar": False})
    lines = [f"<li><b>Stop cost {r['cost']:.1f}s</b> = (lap {r['lap']} + lap {r['lap'] + 1}) minus two normal laps around them.</li>"]
    if g["method"] == "stayed_out":
        refs = ", ".join(f"{code.get(x['driver'], x['driver'])} {x['gain']:+.2f}s" for x in sorted(g["refs"], key=lambda x: -x["gain"])[:8])
        lines.append(f"<li><b>New-tyre gain {g['base']:.2f}s a lap</b>, measured from the {len(g['refs'])} drivers who really did stay out on old {tyre.lower()}s: "
                     f"how much {who} gained on each of them per lap after the stop, compared with before it. Low, base and high are the quarter, middle and three-quarter values. "
                     f"<span class='duel-dim'>{html.escape(refs)}</span></li>")
    else:
        lines.append(f"<li><b>New-tyre gain {g['base']:.2f}s a lap</b> = wear {g['wear']:.3f}s per lap × {g['age_gap']} laps of extra tyre age. Nobody stayed out to compare with, "
                     f"so this is a model, with a range of half to one and a half times.</li>")
    lines.append(f"<li><b>Net</b> = {r['cost']:.1f} − {g['base']:.2f} × {r['laps']} laps = <b>{net['base']:+.1f}s</b>.</li>")
    ok = r["age_needed"] <= r["longest_seen"]
    lines.append(f"<li><b>Would the tyres last?</b> The {tyre.lower()}s would have needed to do {r['age_needed']} laps. The longest anyone ran that tyre in this race was "
                 f"{r['longest_seen']} laps, so {'it was done' if ok else 'nobody proved it possible, and this is a real risk'}.</li>")
    st.markdown("<ul class='duel-list'>" + "".join(lines) + "</ul>", unsafe_allow_html=True)
    st.caption("A simulation, not a fact. It assumes clear track: no time lost in traffic or behind slower cars, no one else changing their plan in response, "
               "and no tyre falling off a cliff. Being on older tyres also makes a car easier to overtake. Positions compare race time after "
               f"lap {cls['base']['lap']}; penalties added after the race are not included. Lap times: OpenF1.")
    move_section(raw, laps, sk, code, num, who, colr)


def _team(raw, num):
    try:
        d = raw["drivers"]
        return str(d[d["driver_number"] == num]["team_name"].iloc[0])
    except Exception:
        return None


def move_section(raw, laps, sk, code, num, who, colr):
    st.markdown("#### What if they had pitted on a different lap?")
    stops = whatif.all_stops(raw, num)
    choices = [(s, whatif.other_laps(raw, laps, num, s)) for s in stops]
    choices = [(s, o) for s, o in choices if o]
    if not choices:
        st.caption(f"No one else made the same tyre change within three laps of {who}, so there is nothing to compare with.")
        return
    c1, c2 = st.columns(2)
    i = c1.selectbox("Stop", range(len(choices)), index=len(choices) - 1, key=f"wi_mv_stop_{sk}_{num}",
                     format_func=lambda i: f"Lap {choices[i][0]['lap']}: {choices[i][0]['old']['compound'].title()} to {choices[i][0]['new']['compound'].title()}")
    stop, others = choices[i]
    opts = list(others)
    lap = c2.selectbox("Pit on lap instead", opts, key=f"wi_mv_lap_{sk}_{num}_{stop['lap']}",
                       format_func=lambda n: f"Lap {n} ({'earlier' if n < stop['lap'] else 'later'}, like {', '.join(code.get(d, str(d)) for d in others[n][:4])}{'…' if len(others[n]) > 4 else ''})")
    r = whatif.move_stop(raw, laps, num, stop, lap)
    if r is None:
        st.caption("Not enough clean laps around this stop to run the numbers.")
        return
    net = r["net"]
    cls = {k: whatif.reclassify(laps, num, net[k]) for k in ("low", "base", "high")}
    pos = _pos(raw, num)

    def finish(k):
        p = cls[k]["places"]
        return f"P{pos - p}" if pos else f"{p:+d} places"

    better = net["base"] > 0
    lo, hi = r["window"]
    m = st.columns(3)
    _card(m[0], f"Laps {lo} to {hi} as driven", f"{r['actual']:.1f}s", f"{who}'s real time over the laps around the stop.", colr)
    _card(m[1], f"Pitting on lap {lap}", f"{abs(net['base']):.1f}s {'faster' if better else 'slower'}", f"Range {net['low']:+.1f}s to {net['high']:+.1f}s (plus = faster).",
          "#43B02A" if better else "#E10600")
    rng = finish("low") if finish("low") == finish("high") else f"{finish('low')} to {finish('high')}"
    _card(m[2], "Finish", f"{'P' + str(pos) + ' → ' if pos else ''}{finish('base')}", f"Range: {rng}.", "#43B02A" if cls["base"]["places"] > 0 else "#9A9AA8")
    names = [f"{code.get(d, d)} (by {t:.1f}s)" for d, t in cls["base"]["passed"]]
    if cls["base"]["places"] > 0:
        verdict = f"On the numbers, pitting on lap {lap} puts {who} ahead of {', '.join(names)} at the flag."
    elif cls["base"]["places"] < 0:
        verdict = f"Pitting on lap {lap} would have cost {who} {-cls['base']['places']} place{'s' if cls['base']['places'] < -1 else ''}."
    else:
        verdict = f"Pitting on lap {lap} changes {who}'s race time but not the finishing place."
    st.markdown(f"<div class='duel-head'>{html.escape(verdict)}</div>", unsafe_allow_html=True)
    refs = ", ".join(f"{code.get(x['driver'], x['driver'])} {x['saved']:+.1f}s" for x in sorted(r["refs"], key=lambda x: -x["saved"]))
    lines = [f"<li><b>How it's worked out:</b> take each driver who really did pit on lap {lap}, and compare their time over laps {lo} to {hi} with {who}'s. "
             f"Their normal pace gap to {who} (from clean laps just before and after) is removed, so only the timing of the stop is left.</li>",
             f"<li><b>Per driver:</b> <span class='duel-dim'>{html.escape(refs)}</span>. Low, base and high are the quarter, middle and three-quarter values.</li>"]
    team = _team(raw, num)
    mates = [code.get(d, str(d)) for d in others[lap] if team and _team(raw, d) == team]
    if mates:
        lines.append(f"<li><b>Double stack:</b> teammate {', '.join(mates)} pitted on lap {lap}. Both cars stopping together means the second one waits, "
                     f"typically a few seconds, which is not included here.</li>")
    st.markdown("<ul class='duel-list'>" + "".join(lines) + "</ul>", unsafe_allow_html=True)
    st.caption("A simulation, not a fact: it assumes clear track and that nobody else reacts. Lap times: OpenF1.")
