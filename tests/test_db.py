import re

from f1analytics.db.loader import delete_session, list_sessions, write_session
from f1analytics.db.queries import list_queries, run_query
from f1analytics.db.schema import schema_sql


def test_ddl_is_postgres_friendly():
    sql = schema_sql().upper()
    assert "SERIAL" not in sql
    for duck_only in ("HUGEINT", "UBIGINT", " LIST", " STRUCT", " MAP("):
        assert duck_only not in sql
    assert re.search(r"\bFLOAT\b", sql) is None


def test_session_loaded_once(db, synthetic_race):
    assert write_session(db, synthetic_race)["skipped"]
    assert len(list_sessions(db)) == 3


def test_force_reload_without_fk_error(db, synthetic_race):
    before = db.execute("SELECT COUNT(*) FROM laps").fetchall()[0][0]
    result = write_session(db, synthetic_race, force=True)
    assert not result["skipped"] and result["telemetry"] > 0
    assert db.execute("SELECT COUNT(*) FROM laps").fetchall()[0][0] == before


def test_telemetry_maps_to_fastest_lap(db, synthetic_quali):
    sid = synthetic_quali.meta["session_id"]
    rows = db.execute(
        """
        SELECT l.driver_code, l.lap_number, l.lap_time_seconds,
               MIN(l2.lap_time_seconds) AS best
        FROM telemetry_samples t JOIN laps l USING (lap_id)
        JOIN laps l2 ON l2.session_id = l.session_id AND l2.driver_code = l.driver_code AND l2.is_accurate
        WHERE l.session_id = ?
        GROUP BY ALL
        """,
        [sid],
    ).fetchall()
    assert len(rows) == 20
    assert all(abs(r[2] - r[3]) < 1e-9 for r in rows)


def test_all_queries_return_rows(db, synthetic_race, synthetic_quali):
    for name in list_queries():
        sid = synthetic_quali.meta["session_id"] if name[:2] in {"06", "07"} else synthetic_race.meta["session_id"]
        assert len(run_query(db, name, session_id=sid)) > 0, name


def test_delete_session(db, synthetic_fp2):
    delete_session(db, synthetic_fp2.meta["session_id"])
    assert len(list_sessions(db)) == 2
