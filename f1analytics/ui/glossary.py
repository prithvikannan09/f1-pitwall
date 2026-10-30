import streamlit as st

TERMS = {
    "Delta": "The difference between two numbers, usually times. Lap delta: +0.5s means this lap was half a second slower than the one you compare it with (your best, or a rival's). Gap delta: if the gap to the car ahead goes from 2.0s to 1.6s, the delta is −0.4s, so you are catching. On the TV the live delta shows whether a driver is up (−, green) or down (+, red) on his best lap right now.",
    "Gap": "How far a car is behind the race leader, in seconds. +12.0s = it would cross the line 12 seconds after the leader.",
    "Interval (Int)": "How far a car is behind the car directly in front of it. Under 1 second at the detection point gives the chasing car Overtake mode.",
    "Lapped (+1 lap)": "The leader has caught and passed this car, so it has done one lap fewer.",
    "Lap": "One full trip round the track. Mexico City GP has 71 laps.",
    "P1, P2…": "Position in the race. P1 is first.",
    "Box": "Team-radio word for 'come into the pits'. Box box = pit this lap.",
    "Pit stop": "The car drives into the pit lane, the crew changes all four tyres in about 2–3 seconds, and the car drives out.",
    "Pit-stop loss": "Total time lost by stopping: slowing down for the pit lane speed limit plus the stop itself. About 20–25 seconds at most tracks.",
    "BOX THIS LAP": "The pit wall wants the driver to come in at the end of this lap.",
    "BOX NEXT LAP": "Get ready, the stop is one lap away.",
    "STAY OUT": "Keep going on the current tyres; stopping now would lose time.",
    "IN PIT": "The car is in the pit lane right now.",
    "Pit window": "The range of laps where stopping gives the best result. Stop too early and the new tyres die before the end; too late and you lose time on old tyres.",
    "Plan A / Plan B": "Plan A is the fastest strategy for the rest of the race. Plan B is the next best one, with how many seconds slower it is.",
    "Strategy": "The plan for when to pit and which tyres to use. 1-stop = one pit stop in the race, 2-stop = two.",
    "Stint": "The laps a driver does on one set of tyres, between two pit stops.",
    "Compound": "The type of tyre. SOFT (red) is fastest but wears out quickest, MEDIUM (yellow) is in between, HARD (white) is slowest but lasts longest. In the timing table S12 means soft tyres, 12 laps old.",
    "Two-compound rule": "In a dry race every driver must use at least two different tyre types, so everyone has to stop at least once.",
    "INTER / WET": "Rain tyres. Inters (green) for a damp track, wets (blue) for heavy rain.",
    "Tyre age": "How many laps the current set of tyres has done.",
    "Tyre wear (degradation, 'deg')": "How much slower the car gets each lap as the tyres wear. 0.06 s/lap means each lap is about six hundredths of a second slower than the one before.",
    "Fresh-tyre gain": "How much faster a car is per lap on brand-new tyres than on its old worn ones.",
    "Undercut": "Pitting before the car ahead. Your new tyres are faster, so while they stay out on old tyres you gain time, and when they pit you can come out in front.",
    "Overcut": "The opposite: staying out longer than the car ahead and hoping your clear-air laps are quicker than their first laps on new tyres.",
    "Undercut threat %": "Out of thousands of simulated stops, how often the undercut worked. 60% = it works in 6 out of 10.",
    "Cover": "Pitting on the same lap as a rival who is trying to undercut you, so they cannot jump ahead.",
    "Rejoin": "Where the car would come back out on track after a pit stop.",
    "Traffic": "Coming out right behind a slower car, which costs time because overtaking is hard.",
    "Double stack": "Both team cars pit on the same lap, one right behind the other. The second car waits a few seconds for its tyres.",
    "Safety Car (SC)": "A road car leads the field slowly after a crash. Everyone bunches up and a pit stop costs about half the usual time, so it is a 'cheap' stop.",
    "Virtual Safety Car (VSC)": "Everyone must drive at a set slower speed, with no real car on track. A pit stop costs less than usual, but not as little as under a Safety Car.",
    "Red flag": "The session is stopped and the cars go to the pit lane. Teams can change tyres for free.",
    "Yellow flag": "Danger on that part of the track: slow down, no overtaking there.",
    "Green flag": "Normal racing.",
    "Chequered flag": "The end of the race or session.",
    "Race control": "The officials running the race. Their messages cover flags, penalties and track limits.",
    "Track limits": "Cars must keep at least part of the car inside the white lines. Doing it too often earns a penalty.",
    "Penalty (5s / 10s)": "Time added to a driver's race, or served at their next pit stop.",
    "Active aero": "New in 2026: the front and rear wings move. They switch between Corner mode (normal, for grip) and Straight mode (flat, for speed) in set zones on the track. It replaced DRS.",
    "Straight mode": "The wing flaps open flat in set zones on the straights so the car is faster. Every driver can use it there, not only the one chasing, so it is not an overtaking aid.",
    "Corner mode": "The normal wing position, giving more grip for the corners. Cars switch back to it before braking.",
    "Overtake mode": "The 2026 overtaking aid that replaced DRS. A driver within 1 second of the car ahead at the detection point (usually the last corner) gets extra battery energy on the next lap, and can keep full electric power to a higher speed than the car in front.",
    "Boost": "The driver presses a button to use stored battery energy for extra speed, to attack or defend. Anyone can use it at any time, as long as there is energy in the battery.",
    "Recharge": "Filling the battery back up, mainly under braking and when lifting off the throttle. Recharging on a straight makes the car slower there.",
    "DRS (until 2025)": "Drag Reduction System, used before 2026: a rear-wing flap that only the chasing car (within 1 second) could open on straights. It no longer exists. Replays of 2025 races still show it.",
    "Speed trap": "A point on the longest straight where every car's speed is measured.",
    "Top speed": "The fastest speed a car reached at the speed trap.",
    "Wing level (downforce)": "How much wing the team has fitted for this track. More wing = more grip in corners but slower on straights, even with Straight mode open. We guess it from top speed, because the real settings are secret.",
    "Dirty air": "The messy, turbulent air coming off a car in front. Following closely through corners, your wings get less clean air, so you lose grip (downforce), slide more and heat your tyres. That's why cars struggle to follow within about a second in fast corners, even when they're quicker.",
    "Clean air": "Air nobody has disturbed: what the leader or a car with a big gap ahead gets. Full grip and cooler tyres, so it's the fastest way to run. Teams pit so a driver comes out in clean air, not stuck behind someone.",
    "Tow / slipstream": "Following close behind another car on a straight. The car in front punches a hole in the air, so the car behind has less drag and goes faster (often 5–15 km/h). The flip side of dirty air: it hurts in corners but helps on straights. In qualifying, teammates sometimes give each other a tow on purpose.",
    "Engine modes": "Settings the driver switches between: more power for attack or defence, less to save fuel or the engine.",
    "Throttle": "The accelerator pedal, 0% to 100%.",
    "Brake": "Whether the driver is braking right now.",
    "RPM": "Engine revolutions per minute: how fast the engine is spinning. F1 engines rev to about 12,000–13,000.",
    "Gear": "F1 cars have 8 forward gears.",
    "Fuel correction": "Cars start with about 105 kg of fuel and get lighter (and faster) as it burns. We remove that effect so we can see the tyre wear alone.",
    "Clean lap": "A normal racing lap, with no pit stop, Safety Car or first-lap chaos, so it is fair to compare.",
    "Out-lap / In-lap": "The lap leaving the pits on new tyres (out-lap) and the lap driving into the pits (in-lap).",
    "Practice (FP1, FP2, FP3)": "Free practice: sessions before qualifying where teams test setups and tyres. Times do not count for the race.",
    "Long run": "In practice, many laps in a row on one set of tyres to copy race conditions. It is the best clue to Sunday's pace.",
    "Qualifying": "The timed session that sets the starting order (the grid). Fastest single lap starts at the front (pole).",
    "Team radio": "Messages between the driver and their engineer. F1 makes some of them public a short time after they air.",
    "Clipping": "When the battery runs low near the end of a straight, the car stops accelerating or even slows while the driver is still flat out.",
    "Deployment": "Using the battery's electric power. Where and how hard a team deploys decides who is fastest on each straight.",
    "Late braking": "Hitting the brakes later than others into a corner. It gains time and helps overtaking, but risks running wide.",
    "Racecraft": "How good a driver is in wheel-to-wheel fights: attacking, defending and avoiding contact.",
    "Percentile score": "0 to 100 compared with this season's drivers. 50 is average; 90 means better than 9 in 10.",
    "Attack score": "0–100: how often a driver turns 'within a second of the car ahead' into a completed pass on track, compared with this season's grid.",
    "Defence score": "0–100: how often a driver keeps his place when a car is within a second behind him, compared with this season's grid.",
    "Race pace": "How fast a driver is over a whole race, using his typical clean lap with the fuel effect removed. Different from one-lap qualifying speed.",
    "Tyre care": "How slowly a driver's tyres lose grip compared with others on the same tyre. Good tyre care means longer stints or fewer stops.",
    "Fuel-corrected lap": "A lap time adjusted as if the car carried the same fuel all race, so early heavy laps and late light laps can be compared fairly.",
    "Places gained": "Starting position minus finishing position, averaged over the season. +2 means he usually finishes two places higher than he starts.",
    "Podium": "Finishing in the top three (P1, P2 or P3). The three drivers stand on the podium after the race.",
    "Beat teammate %": "How often a driver finishes ahead of his teammate, who has the same car. The fairest way to compare drivers, because the car is taken out.",
    "Strongest track": "A track where a driver is usually quicker than his own normal pace that season (and against his teammate).",
    "Bogey track": "A track where a driver is usually furthest below his own normal level, even if he has done well there.",
    "Head to head chance": "The app replays the rest of the race thousands of times with small random changes (pace, stops, Safety Cars) and counts how often one driver finishes ahead.",
    "Style tags": "Short labels from the scores: Hunter (strong attack), The wall (strong defence), Rocket starts, Tyre whisperer, Race-pace king, Late braker, Strong on the straights, Patient (rarely forces passes), Can be passed (weaker defence).",
    "est.": "An estimate: worked out by us from public data, not an official number.",
}

SECTIONS = {
    "styles": ["Attack score", "Defence score", "Style tags", "Race pace", "Tyre care", "Late braking", "Deployment", "Clipping",
               "Places gained", "Podium", "Beat teammate %", "Strongest track", "Bogey track", "Head to head chance", "Percentile score"],
    "call": ["BOX THIS LAP", "STAY OUT", "Pit window", "Plan A / Plan B", "Delta", "Pit-stop loss", "Rejoin", "Traffic", "Undercut", "Cover", "Undercut threat %", "Safety Car (SC)", "Virtual Safety Car (VSC)", "Tyre wear (degradation, 'deg')", "Double stack"],
    "car": ["Active aero", "Straight mode", "Overtake mode", "Boost", "Recharge", "Speed trap", "Top speed", "Wing level (downforce)", "Tow / slipstream", "Dirty air", "Clean air", "Throttle", "RPM", "est."],
    "timing": ["P1, P2…", "Gap", "Interval (Int)", "Delta", "Dirty air", "Overtake mode", "Lapped (+1 lap)", "Compound", "Box"],
    "practice": ["Practice (FP1, FP2, FP3)", "Long run", "Tyre wear (degradation, 'deg')", "Fuel correction", "Delta", "Out-lap / In-lap"],
}

STATUS_PLAIN = {
    "1": "Green flag: normal racing.",
    "2": "Yellow flag: danger somewhere on track, drivers must slow down there and not overtake.",
    "4": "Safety Car: everyone follows a road car slowly while a crash is cleared. Pit stops are cheap right now.",
    "5": "Red flag: the session is stopped.",
    "6": "Virtual Safety Car: everyone drives at a set slower speed. Pit stops cost less than usual.",
    "7": "The Virtual Safety Car is ending; racing restarts in a moment.",
}


def beginner_on():
    return bool(st.session_state.get("pw_beginner", True))


def sidebar_toggle():
    default = str(st.query_params.get("beginner", "1")).lower() not in ("0", "false", "off", "no")
    st.session_state.setdefault("pw_beginner", default)
    st.sidebar.toggle("Beginner mode", key="pw_beginner", help="Explains every F1 word and each pit-wall call in plain English.")


def words(section, title="What do these words mean?"):
    if not beginner_on():
        return
    with st.expander(f"📖 {title}"):
        st.markdown("\n".join(f"- **{t}:** {TERMS[t]}" for t in SECTIONS[section]))


def plain(text):
    if beginner_on() and text:
        st.markdown(f"<div class='pw-plain'>💡 {text}</div>", unsafe_allow_html=True)


def status_text(status):
    return STATUS_PLAIN.get(str(status), "")


def explain_call(r):
    car = r["car"]
    who = car["code"]
    tyre = (car.get("compound") or "current").lower()
    age = car.get("tyre_age")
    window = r.get("window")
    plan = r.get("best_plan") or {}
    call = r["call"]
    lap = r.get("lap")
    if call == "BOX THIS LAP":
        out = f"The team's best move is for {who} to pit at the end of this lap for fresh tyres. Waiting longer would cost more time than the stop itself."
    elif call == "BOX NEXT LAP":
        out = f"{who} should pit next time round. The crew is getting the tyres ready."
    elif call == "IN PIT":
        out = f"{who} is in the pit lane right now, changing tyres."
    elif plan and not plan.get("stops"):
        out = f"{who} keeps going. The {tyre} tyres ({age} laps old) can last to the finish, so no more stops are needed."
    elif window:
        out = f"{who} keeps going on the {tyre} tyres ({age} laps old). The best time to stop is between laps {window[0]} and {window[1]}."
    else:
        out = f"{who} keeps going: the {tyre} tyres ({age} laps old) are still quick enough that stopping now would lose time."
    rj = r.get("rejoin_now")
    if rj and call != "IN PIT":
        out += f" If {who} stopped now they would come out in P{rj['position']}" + (", stuck behind a slower car." if rj.get("traffic") else ".")
    d = r.get("defend")
    if d and d.get("probability") is not None and d["probability"] >= 0.4:
        out += f" Watch {d['attacker']} behind: if they pit first they could jump ahead on newer tyres (the 'undercut'), so {who} may need to pit on the same lap."
    a = r.get("attack")
    if a and a.get("probability") is not None and a["probability"] >= 0.5:
        out += f" Chance to attack: pitting before {a['target']} ahead gives about a {a['probability'] * 100:.0f}% chance to pass them in the stops."
    return out


def glossary(key="main"):
    if not beginner_on():
        return
    with st.expander("📖 F1 words explained (A–Z)"):
        q = st.text_input("Search a word", key=f"gl_q_{key}", placeholder="e.g. delta, undercut, overtake mode").strip().lower()
        hits = [(t, d) for t, d in sorted(TERMS.items(), key=lambda kv: kv[0].lower()) if not q or q in t.lower() or q in d.lower()]
        if not hits:
            st.caption("No match. Try another word.")
        st.markdown("\n".join(f"- **{t}:** {d}" for t, d in hits))


FLAGS = [
    ("Green", "#1E9E5A", "Track is clear. Normal racing, overtaking allowed."),
    ("Yellow", "#F5C518", "Danger near the track in that zone (a stopped car, debris). Slow down, no overtaking there."),
    ("Double yellow", "repeating-linear-gradient(90deg,#F5C518 0 45%,transparent 45% 55%,#F5C518 55%)", "Serious danger, often marshals on track. Slow right down and be ready to stop. No overtaking there."),
    ("Red", "#E10600", "Session stopped. All cars drive slowly to the pit lane. Teams may change tyres for free."),
    ("Blue", "#2563EB", "A faster car is about to lap you: let it past. Ignoring it three times earns a penalty. In practice it means a car on a fast lap is coming."),
    ("Black and white", "linear-gradient(135deg,#111 50%,#F9FAFB 50%)", "Warning to one driver for bad behaviour or going off track too often (track limits). Next time is a penalty."),
    ("Black with orange circle", "radial-gradient(circle,#F97316 0 34%,#111 36%)", "That car has damage or a problem (loose part, smoke) and must come into the pits to fix it."),
    ("Black", "#111111", "That driver is disqualified and must return to the pits."),
    ("Red and yellow stripes", "repeating-linear-gradient(90deg,#E10600 0 20%,#F5C518 20% 40%)", "Slippery track in that zone: oil, water or gravel on the racing line."),
    ("White", "#F9FAFB", "A slow vehicle ahead in that zone, like a recovery truck or a car limping back."),
    ("Chequered", "repeating-conic-gradient(#111 0 25%,#F9FAFB 0 50%) 0 0/12px 12px", "End of the race or session."),
    ("SC board", "#F5C518", "Safety Car: everyone follows a road car slowly in a line, no overtaking, while a crash is cleared."),
    ("VSC board", "#F5C518", "Virtual Safety Car: everyone drives to a set slower speed shown on their dashboard, no overtaking."),
]

_FLAG_RULES = [
    (r"DOUBLE YELLOW", "Double yellow"),
    (r"BLACK AND WHITE", "Black and white"),
    (r"BLACK AND ORANGE|MECHANICAL", "Black with orange circle"),
    (r"\bBLACK FLAG\b|DISQUALIFIED", "Black"),
    (r"CHEQUERED", "Chequered"),
    (r"RED FLAG", "Red"),
    (r"BLUE FLAG", "Blue"),
    (r"SLIPPERY", "Red and yellow stripes"),
    (r"\bYELLOW\b", "Yellow"),
    (r"VIRTUAL SAFETY CAR|\bVSC\b", "VSC board"),
    (r"SAFETY CAR", "SC board"),
    (r"^CLEAR IN|TRACK CLEAR|GREEN FLAG", "Green"),
]
FLAG_INFO = {n: (c, m) for n, c, m in FLAGS}


def flag_for(message):
    import re

    text = str(message or "").upper()
    for pattern, name in _FLAG_RULES:
        if re.search(pattern, text):
            return name
    return None


def swatch(name, size=18):
    colour = FLAG_INFO[name][0]
    return (f"<span style='display:inline-block;width:{size + 8}px;height:{size}px;border-radius:3px;vertical-align:middle;"
            f"margin-right:6px;border:1px solid rgba(128,128,128,0.6);background:{colour}'></span>")


OTHER_NOTES = [
    (r"OVERTAKE ENABLED", "Overtake mode is switched on: a driver within 1 second of the car ahead now gets extra battery power to attack."),
    (r"OVERTAKE DISABLED", "Overtake mode is switched off for now (usually at the start, in rain or under a Safety Car)."),
    (r"DRS ENABLED", "DRS is switched on: the chasing car can open its rear-wing flap (2025 and earlier)."),
    (r"DRS DISABLED", "DRS is switched off for now (2025 and earlier)."),
    (r"MARSHALS ON TRACK", "Track workers are on the track clearing something. Drivers must slow right down there."),
    (r"PIT EXIT CLOSED", "Cars cannot leave the pit lane right now."),
    (r"PIT EXIT OPEN", "Cars can leave the pit lane."),
    (r"PIT ENTRY CLOSED", "Cars cannot come into the pits right now, except for an emergency."),
    (r"TRACK LIMITS|DELETED", "The driver went off the track (all four wheels past the white line), so that lap time does not count. Repeat offences get a warning flag, then a penalty."),
    (r"UNDER INVESTIGATION", "The stewards (the referees) are looking at an incident. A penalty may follow."),
    (r"NO FURTHER (ACTION|INVESTIGATION)", "The stewards looked at it and decided no penalty."),
    (r"PENALTY", "The stewards have punished a driver, usually with seconds added to their race time or served at their next pit stop."),
    (r"NOTED", "Race control has seen an incident and may look into it."),
    (r"SAFETY CAR IN THIS LAP", "The Safety Car comes in at the end of this lap and racing restarts."),
    (r"RISK OF RAIN", "Rain is possible. Watch for teams fitting inters (green) or wets (blue)."),
]


def flag_note(message):
    import re

    text = str(message or "").upper()
    name = flag_for(message)
    if not name or (name == "SC board" and "IN THIS LAP" in text):
        for pattern, note in OTHER_NOTES:
            if re.search(pattern, text):
                return note
        return ""
    meaning = FLAG_INFO[name][1]
    if name == "Green" and "SECTOR" in text:
        meaning = "The danger in that zone is gone; racing is back to normal there."
    if "SECTOR" in text:
        meaning += " (Sector = one of about 20 small marshal zones.)"
    return swatch(name, 12) + meaning


def flags_panel(key="main"):
    if not beginner_on():
        return
    with st.expander("🏁 Flags explained"):
        st.markdown(
            "".join(f"<div style='margin:6px 0'>{swatch(n)}<b>{n}:</b> {m}</div>" for n, _, m in FLAGS)
            + "<div class='pw-sub' style='margin-top:8px'>Marshals wave flags at posts round the track; drivers also see them as lights on track and on their steering-wheel screen.</div>",
            unsafe_allow_html=True,
        )
