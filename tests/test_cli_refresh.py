import pandas as pd
import pytest

from f1analytics.cli import main
from f1analytics.db.schema import connect, init_db
from f1analytics.refresh import due_sessions, refresh
from f1analytics.sources import SyntheticSource


def test_setup_and_query(tmp_path, capsys):
    db = str(tmp_path / "f1.duckdb")
    assert main(["--db", db, "load", "--source", "synthetic", "--sessions", "Q", "R"]) == 0
    assert main(["--db", db, "list"]) == 0
    assert main(["--db", db, "query", "02_speed_trap_leaderboard", "--limit", "3"]) == 0
    out = capsys.readouterr().out
    assert "2024_20_R" in out and "top_speed_kmh" in out


def test_due_sessions_respects_date():
    con = init_db(connect(":memory:"))
    keys = due_sessions(SyntheticSource(), con, 2024, as_of=pd.Timestamp("2024-03-03 12:00"))
    assert {k.session for k in keys} == {"FP1", "FP2", "FP3", "Q", "R"}
    assert all(k.gp == 1 for k in keys)
    later = due_sessions(SyntheticSource(), con, 2024, as_of=pd.Timestamp("2024-03-10 12:00"), sessions=["R"])
    assert [k.gp for k in later] == [1, 2]


def test_refresh_skips_stored_sessions():
    con = init_db(connect(":memory:"))
    first = refresh(con, [2024], as_of=pd.Timestamp("2024-03-03 12:00"), source_mode="synthetic", sessions=["R"], telemetry_mode="none")
    second = refresh(con, [2024], as_of=pd.Timestamp("2024-03-03 12:00"), source_mode="synthetic", sessions=["R"], telemetry_mode="none")
    assert len(first["loaded"]) == 1 and len(second["loaded"]) == 0


def test_refresh_never_uses_auto():
    with pytest.raises(ValueError):
        refresh(None, [2024], source_mode="auto")


def test_refresh_reports_failures(monkeypatch):
    con = init_db(connect(":memory:"))
    monkeypatch.setattr(SyntheticSource, "load", lambda self, key, *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    report = refresh(con, [2024], as_of=pd.Timestamp("2024-03-03 12:00"), source_mode="synthetic", sessions=["R"])
    assert report["failed"] and not report["loaded"]
