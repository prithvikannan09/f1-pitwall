from pathlib import Path

from streamlit.testing.v1 import AppTest

from f1analytics.ui.glossary import SECTIONS, TERMS, explain_call

PAGE = str(Path(__file__).resolve().parent.parent / "pages" / "1_Pit_Wall.py")


def test_every_section_term_is_defined():
    for terms in SECTIONS.values():
        for t in terms:
            assert t in TERMS and len(TERMS[t]) > 20


def test_2026_terms_replace_drs():
    assert "Overtake mode" in TERMS and "Straight mode" in TERMS and "Boost" in TERMS
    assert "DRS" not in TERMS
    assert "no longer exists" in TERMS["DRS (until 2025)"]
    assert not any("DRS" == t for s in SECTIONS.values() for t in s)


def _r(call, **kw):
    r = {"call": call, "car": {"code": "HAM", "compound": "MEDIUM", "tyre_age": 18}, "window": (20, 26),
         "best_plan": {"stops": 1}, "rejoin_now": {"position": 9, "traffic": True}, "defend": None, "attack": None}
    r.update(kw)
    return r


def test_explain_call_plain_words():
    assert "pit at the end of this lap" in explain_call(_r("BOX THIS LAP"))
    s = explain_call(_r("STAY OUT", defend={"attacker": "RUS", "probability": 0.6}))
    assert "laps 20 and 26" in s and "P9" in s and "RUS" in s and "undercut" in s
    assert "no more stops" in explain_call(_r("STAY OUT", best_plan={"stops": 0}))


def _run(beginner):
    at = AppTest.from_file(PAGE, default_timeout=120)
    at.query_params["beginner"] = "1" if beginner else "0"
    at.run()
    at.sidebar.radio[0].set_value("Replay").run()
    at.slider(key="pw_lap").set_value(14).run()
    assert not at.exception and not at.error
    return " ".join(m.value for m in at.markdown), [e.label for e in at.expander]


def test_beginner_mode_on_and_off():
    text, exps = _run(True)
    assert "💡" in text and "pit at the end of this lap" in text
    assert any("F1 words explained" in e for e in exps) and any("Strategy words" in e for e in exps)
    text, exps = _run(False)
    assert "💡" not in text and not any("📖" in e for e in exps)


def test_flags_from_real_race_control():
    from f1analytics.ui.glossary import flag_for, flag_note

    cases = {
        "DOUBLE YELLOW IN TRACK SECTOR 10": "Double yellow",
        "BLACK AND WHITE FLAG FOR CAR 63 (RUS) - TRACK LIMITS": "Black and white",
        "WAVED BLUE FLAG FOR CAR 44 (HAM) TIMED AT 20:31:02": "Blue",
        "TRACK SURFACE SLIPPERY IN TRACK SECTOR 11": "Red and yellow stripes",
        "CLEAR IN TRACK SECTOR 5": "Green",
        "CHEQUERED FLAG": "Chequered",
        "RED FLAG": "Red",
        "VIRTUAL SAFETY CAR DEPLOYED": "VSC board",
        "SAFETY CAR DEPLOYED": "SC board",
        "YELLOW IN TRACK SECTOR 3": "Yellow",
        "CAR 16 (LEC) TIME 1:17.9 DELETED - TRACK LIMITS AT TURN 4": None,
    }
    for msg, want in cases.items():
        assert flag_for(msg) == want, msg
    assert "marshal zones" in flag_note("DOUBLE YELLOW IN TRACK SECTOR 10")
    assert "Overtake mode is switched on" in flag_note("OVERTAKE ENABLED")
    assert "does not count" in flag_note("CAR 16 (LEC) TIME 1:17.9 DELETED - TRACK LIMITS AT TURN 4")
    assert "restarts" in flag_note("SAFETY CAR IN THIS LAP")
    assert flag_note("FIA STEWARDS: SOMETHING ELSE") == ""


def test_flags_shown_in_page():
    at = AppTest.from_file(PAGE, default_timeout=120)
    at.run()
    at.sidebar.radio[0].set_value("Replay").run()
    at.slider(key="pw_lap").set_value(56).run()
    assert not at.exception and not at.error
    assert any("Flags explained" in e.label for e in at.expander)
    text = " ".join(m.value for m in at.markdown)
    assert "End of the race or session" in text
