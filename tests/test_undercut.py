import pytest

from f1analytics.analysis.undercut import rejoin_gap, undercut_margin


def test_doc_defaults_fail_by_1_85():
    r = undercut_margin(3.2)
    assert r.final_gap == pytest.approx(1.85)
    assert not r.success


def test_small_gap_works():
    r = undercut_margin(1.0)
    assert r.final_gap == pytest.approx(-0.35)
    assert r.success


def test_pit_loss_now_matters():
    a = undercut_margin(3.2, pit_loss=22.0, pit_loss_target=22.0).final_gap
    b = undercut_margin(3.2, pit_loss=23.0, pit_loss_target=22.0).final_gap
    assert b - a == pytest.approx(1.0)


def test_rival_slow_stop_helps():
    assert undercut_margin(3.2, pit_loss_target=25.0).final_gap == pytest.approx(1.85 - 3.0)


def test_longer_window_adds_gain_and_rival_outlap():
    k1 = undercut_margin(3.2, k=1)
    k2 = undercut_margin(3.2, k=2)
    assert k2.breakdown["Fresh-tyre gain while rival stays out"] == pytest.approx(-(1.4 + 1.43))
    assert k2.breakdown["Rival out-lap (warm-up − your tyre age)"] == pytest.approx(-(0.8 - 0.1))
    assert k2.final_gap < k1.final_gap


def test_traffic_rule():
    assert rejoin_gap(22.0, [1.5, 21.5, 30]) == pytest.approx(0.5)
    assert rejoin_gap(22.0, [30]) is None
    clear = undercut_margin(3.2, field_gaps=(30.0,))
    stuck = undercut_margin(3.2, field_gaps=(21.5,), pass_prob=0.3)
    assert not clear.stuck_in_traffic and stuck.stuck_in_traffic
    assert stuck.final_gap - clear.final_gap == pytest.approx(2 * 0.6)
