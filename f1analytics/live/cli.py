import argparse
import logging
import sys
import time

from f1analytics.live.recorder import CURRENT, LIVE_DIR, record, write_json_atomic


def cmd_record(args):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    print(f"Recording F1 live timing into {args.dir} (Ctrl+C to stop). Open the Pit Wall page in Live mode.")
    try:
        record(args.dir)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def cmd_check(args):
    from f1analytics.live.auth import subscription_token
    from f1analytics.live.signalr import AUTH_TOPICS, TOPICS, connect_once, decode

    token = subscription_token()
    ws = connect_once(TOPICS + (AUTH_TOPICS if token else []), access_token=token)
    try:
        while True:
            for msg in decode(ws.recv(timeout=15)):
                if msg.get("type") == 3:
                    res = msg.get("result") or {}
                    info = res.get("SessionInfo") or {}
                    lines = ((res.get("TimingData") or {}).get("Lines") or {})
                    print(f"OK: live feed reachable. Latest session: {(info.get('Meeting') or {}).get('Name')} {info.get('Name')} "
                          f"({(res.get('SessionStatus') or {}).get('Status')}), {len(lines)} cars in timing.")
                    if token:
                        got = [t for t in AUTH_TOPICS if res.get(t)]
                        print(f"F1TV: signed in; {'GPS positions and car data received' if len(got) == 2 else 'signed in, but no GPS data in this snapshot (normal between sessions)'}.")
                    else:
                        print("F1TV: not signed in (free data only). Run: python -m f1analytics live login")
                    return 0
    finally:
        ws.close()


def cmd_login(args):
    from f1analytics.live.auth import login_interactive

    print("Signing in to your F1TV account. FastF1 asks for your email and password here, in your own terminal; they go only to Formula 1 and are not saved (only a token that lasts a few days).")
    st = login_interactive()
    if st.get("signed_in"):
        import datetime

        exp = datetime.datetime.fromtimestamp(st["expires_at"]).strftime("%a %d %b %H:%M")
        print(f"OK: signed in to F1TV. Token valid until {exp}.")
        return 0
    print("Sign-in did not complete.")
    return 1


def cmd_demo(args):
    from pathlib import Path

    from f1analytics.live.replay import RaceReplay, load_fixture, load_openf1_race

    if args.gp:
        rep = RaceReplay(load_openf1_race(args.year, args.gp))
    else:
        rep = RaceReplay(load_fixture(Path(__file__).resolve().parent.parent / "replays" / "usgp2026"))
    print(f"Demo: replaying {rep.raw['event']['EventName']} into {args.dir} as if live, one lap every {args.seconds}s. Ctrl+C to stop.")
    try:
        for lap in range(args.start, rep.total_laps + 1):
            snap = rep.snapshot(lap)
            snap["source"] = "demo"
            snap["feed"] = {"connected": True, "demo": True}
            write_json_atomic(Path(args.dir) / CURRENT, snap)
            print(f"  lap {lap}/{rep.total_laps}", end="\r", flush=True)
            time.sleep(args.seconds)
    except KeyboardInterrupt:
        pass
    print()
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m f1analytics live", description="Live timing for the pit wall")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record", help="connect to F1 live timing and keep the pit wall fed")
    r.add_argument("--dir", default=str(LIVE_DIR))
    r.set_defaults(func=cmd_record)
    lg = sub.add_parser("login", help="sign in to F1TV for live car positions and car data")
    lg.set_defaults(func=cmd_login)
    c = sub.add_parser("check", help="test that the live feed is reachable")
    c.set_defaults(func=cmd_check)
    d = sub.add_parser("demo", help="replay a past race into the live pit wall")
    d.add_argument("--dir", default=str(LIVE_DIR))
    d.add_argument("--seconds", type=float, default=3.0, help="seconds per lap")
    d.add_argument("--start", type=int, default=1)
    d.add_argument("--year", type=int, default=2025)
    d.add_argument("--gp", default=None, help="leave empty for the bundled 2026 US GP")
    d.set_defaults(func=cmd_demo)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
