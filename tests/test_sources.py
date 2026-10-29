from unittest import mock

import pandas as pd
import pytest

import f1analytics.sources as sources
from f1analytics.columns import LAP_COLUMNS, conform
from f1analytics.sources import SessionKey, get_source, load_with_fallback, normalise_session


def test_auto_falls_back_to_synthetic_when_offline():
    with mock.patch.object(sources, "online", return_value=False):
        with mock.patch("f1analytics.sources.fastf1_source.FastF1Source.load", side_effect=RuntimeError("no cache")):
            sd = load_with_fallback(SessionKey(2024, "Mexico", "R"), mode="auto")
    assert sd.meta["data_source"] == "synthetic"


def test_get_source_synthetic():
    assert get_source("synthetic").name == "synthetic"


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        get_source("bogus")


def test_conform_adds_missing_columns():
    out = conform(pd.DataFrame({"Driver": ["VER"]}), LAP_COLUMNS)
    assert set(LAP_COLUMNS) <= set(out.columns)
    assert pd.isna(out.loc[0, "LapTime"])


def test_session_aliases():
    assert normalise_session("Race") == "R"
    assert normalise_session("qualifying") == "Q"
    assert normalise_session("Practice 2") == "FP2"
    with pytest.raises(ValueError):
        normalise_session("warmup")


def test_fastf1_adapter_uses_pick_drivers():
    from f1analytics.sources.fastf1_source import FastF1Source

    session = mock.MagicMock()
    lap = mock.MagicMock()
    lap.empty = False
    lap.get_car_data.return_value.add_distance.return_value = pd.DataFrame({"Speed": [100.0], "Distance": [0.0]})
    session.laps.pick_drivers.return_value.pick_fastest.return_value = lap
    tel = FastF1Source._telemetry_fn(session)("VER", -1)
    session.laps.pick_drivers.assert_called_once_with("VER")
    session.laps.pick_driver.assert_not_called()
    assert tel.loc[0, "Speed"] == 100.0
