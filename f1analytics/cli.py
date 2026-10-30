import argparse
import sys
import warnings

import pandas as pd

from f1analytics import config
from f1analytics.db.loader import list_sessions, write_session
from f1analytics.db.queries import latest_session_id, list_queries, query_sql, run_query
from f1analytics.db.schema import connect, init_db
from f1analytics.sources import SessionKey, load_with_fallback

warnings.filterwarnings("ignore", category=FutureWarning)


def cmd_init(args):
    init_db(connect(args.db)).close()
    print(f"Database ready: {args.db or config.DB_PATH}")
    return 0


def cmd_load(args):
    con = init_db(connect(args.db))
    status = 0
    for code in args.sessions:
        key = SessionKey(args.year, args.gp, code)
        try:
            data = load_with_fallback(key, mode=args.source)
            result = write_session(con, data, telemetry_mode=args.telemetry, force=args.force)
        except Exception as exc:
            print(f"FAILED {args.year} {args.gp} {code}: {exc}")
            status = 1
            continue
        if result.get("skipped"):
            print(f"{result['session_id']}: already loaded (use --force to reload)")
        else:
            print(f"{result['session_id']}: {result['laps']} laps, {result['telemetry']} telemetry rows, {result['weather']} weather rows  [source: {result['source']}]")
            if result["source"] == "synthetic":
                print("  note: no real data reachable, so this is SAMPLE data, not the real session")
    con.close()
    return status


def cmd_setup(args):
    args.year, args.gp, args.sessions = config.DEFAULT_YEAR, config.DEFAULT_GP, ["FP2", "Q", "R"]
    cmd_init(args)
    return cmd_load(args)


def cmd_list(args):
    con = init_db(connect(args.db))
    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(list_sessions(con).to_string(index=False))
    con.close()
    return 0


def cmd_query(args):
    if not args.name:
        print("Available queries:")
        for q in list_queries():
            print(f"  {q}")
        return 0
    con = init_db(connect(args.db))
    sid = args.session or latest_session_id(con)
    if sid is None:
        print("Database is empty. Run: python -m f1analytics setup")
        return 1
    if args.show_sql:
        print(query_sql(args.name))
    df = run_query(con, args.name, session_id=sid)
    with pd.option_context("display.width", 160, "display.max_columns", 20, "display.max_rows", args.limit):
        print(f"session: {sid}\n")
        print(df.head(args.limit).to_string(index=False))
    con.close()
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="python -m f1analytics", description="F1 strategy and telemetry engine")
    p.add_argument("--db", default=None, help="database file (default data/f1.duckdb)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="create the database and load 2024 Mexico FP2, Q and R").set_defaults(func=cmd_setup, source="auto", telemetry="fastest", force=False)
    sub.add_parser("init", help="create empty tables").set_defaults(func=cmd_init)
    load = sub.add_parser("load", help="load sessions into the database")
    load.add_argument("--year", type=int, default=config.DEFAULT_YEAR)
    load.add_argument("--gp", default=config.DEFAULT_GP, help="name, city, country or round number")
    load.add_argument("--sessions", nargs="+", default=["Q", "R"])
    load.add_argument("--source", choices=["auto", "openf1", "fastf1", "synthetic"], default="auto")
    load.add_argument("--telemetry", choices=["none", "fastest", "all"], default="fastest")
    load.add_argument("--force", action="store_true", help="reload even if already stored")
    load.set_defaults(func=cmd_load)
    sub.add_parser("list", help="show stored sessions").set_defaults(func=cmd_list)
    q = sub.add_parser("query", help="run an example SQL query")
    q.add_argument("name", nargs="?")
    q.add_argument("--session", default=None)
    q.add_argument("--show-sql", action="store_true")
    q.add_argument("--limit", type=int, default=25)
    q.set_defaults(func=cmd_query)
    sub.add_parser("refresh", help="load every finished session not yet stored (see: refresh --help)")
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "styles":
        import logging

        from f1analytics.pitwall import racecraft

        logging.basicConfig(level=logging.INFO, format="%(message)s")
        years = [int(x) for x in argv[1:] if x.isdigit()]
        year = years[0] if years else 2026
        data = racecraft.build(year, telemetry="--no-telemetry" not in argv)
        print(f"Built driver styles from {len(data['races'])} races for {len(data['profiles'])} drivers.")
        if "--no-history" not in argv:
            hist = racecraft.build_history(tuple(range(2023, year + 1)))
            print(f"Built track history: {len(hist['rows'])} driver-races since 2023.")
        return 0
    if argv and argv[0] == "live":
        from f1analytics.live.cli import main as live_main

        return live_main(argv[1:])
    if "refresh" in argv:
        i = argv.index("refresh")
        from f1analytics.refresh import main as refresh_main

        db = argv[argv.index("--db") + 1] if "--db" in argv[:i] else None
        rest = argv[i + 1:] + (["--db", db] if db else [])
        return refresh_main(rest)
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
