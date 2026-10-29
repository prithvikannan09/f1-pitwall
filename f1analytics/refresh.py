import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from f1analytics import config
from f1analytics.db.loader import session_exists, write_session
from f1analytics.db.schema import connect, init_db
from f1analytics.sources import SessionKey, get_source, normalise_session
from f1analytics.sources.base import make_session_id

NAME_TO_CODE = {
    "Practice 1": "FP1", "Practice 2": "FP2", "Practice 3": "FP3",
    "Qualifying": "Q", "Race": "R", "Sprint": "S",
    "Sprint Qualifying": "SQ", "Sprint Shootout": "SQ",
}

log = logging.getLogger("f1analytics.refresh")


def _utc(value):
    ts = pd.Timestamp(value)
    if ts is pd.NaT or pd.isna(ts):
        return None
    return ts.tz_convert("UTC").tz_localize(None) if ts.tzinfo else ts


def due_sessions(source, con, year, as_of=None, min_age_hours=config.REFRESH_MIN_AGE_HOURS, sessions="all"):
    as_of = _utc(as_of or datetime.now(timezone.utc))
    wanted = None if sessions == "all" else {normalise_session(s) for s in sessions}
    sched = source.schedule(year)
    due = []
    for _, event in sched.iterrows():
        for i in range(1, 6):
            name = event.get(f"Session{i}")
            code = NAME_TO_CODE.get(str(name))
            start = _utc(event.get(f"Session{i}DateUtc"))
            if code is None or start is None or (wanted and code not in wanted):
                continue
            if start + timedelta(hours=min_age_hours) > as_of:
                continue
            sid = make_session_id(year, event["RoundNumber"], code)
            if con is not None and session_exists(con, sid):
                continue
            due.append(SessionKey(int(year), int(event["RoundNumber"]), code))
    return due


def refresh(con, years, as_of=None, source_mode="openf1", sessions="all", telemetry_mode="fastest"):
    if source_mode == "auto":
        raise ValueError("refresh never uses auto mode; pick openf1 or fastf1, or synthetic for a dry run")
    source = get_source(source_mode)
    report = {"loaded": [], "failed": [], "skipped": 0}
    for year in years:
        for key in due_sessions(source, con, year, as_of, sessions=sessions):
            try:
                data = source.load(key)
                result = write_session(con, data, telemetry_mode=telemetry_mode)
                report["loaded"].append(result)
                log.info("loaded %s (%s laps)", result["session_id"], result.get("laps"))
            except Exception as exc:
                report["failed"].append({"session": f"{key.year} round {key.gp} {key.session}", "error": str(exc)})
                log.error("failed %s: %s", key, exc)
    return report


def setup_logging():
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(config.LOG_DIR / "refresh.log"), logging.StreamHandler(sys.stdout)],
    )


def main(argv=None):
    parser = argparse.ArgumentParser(prog="refresh", description="Load every finished F1 session that is not yet in the database.")
    parser.add_argument("--year", type=int, action="append", help="season to refresh (repeatable); default this year")
    parser.add_argument("--sessions", nargs="+", default=["all"], help="e.g. Q R, default all")
    parser.add_argument("--source", choices=["openf1", "fastf1", "synthetic"], default="openf1")
    parser.add_argument("--telemetry", choices=["none", "fastest", "all"], default="fastest")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)
    setup_logging()
    years = args.year or [datetime.now(timezone.utc).year]
    sessions = "all" if args.sessions == ["all"] else args.sessions
    con = init_db(connect(args.db))
    report = refresh(con, years, source_mode=args.source, sessions=sessions, telemetry_mode=args.telemetry)
    con.close()
    print(f"Loaded {len(report['loaded'])} session(s), {len(report['failed'])} failed.")
    for f in report["failed"]:
        print(f"  FAILED {f['session']}: {f['error']}")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
