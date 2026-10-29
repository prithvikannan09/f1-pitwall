import logging
import os
import socket
import warnings

from f1analytics.sources.base import DataSource, SessionData, SessionKey
from f1analytics.sources.codes import normalise_session
from f1analytics.sources.synthetic import SyntheticSource

HOSTS = {"openf1": ("api.openf1.org", 443), "fastf1": ("livetiming.formula1.com", 443)}
MODES = {"auto", "openf1", "fastf1", "synthetic"}
log = logging.getLogger("f1analytics.sources")


def online(name="openf1", timeout=3.0):
    try:
        with socket.create_connection(HOSTS[name], timeout=timeout):
            return True
    except OSError:
        return False


def has_f1_login():
    return bool(os.environ.get("F1_USERNAME") and os.environ.get("F1_PASSWORD"))


def resolve_mode(mode=None):
    mode = (mode or os.environ.get("F1_SOURCE") or "auto").lower()
    if mode not in MODES:
        raise ValueError(f"Unknown source mode {mode!r}; use one of {', '.join(sorted(MODES))}")
    return mode


def _openf1():
    from f1analytics.sources.openf1_source import OpenF1Source

    return OpenF1Source()


def _fastf1(offline=False):
    from f1analytics.sources.fastf1_source import FastF1Source

    return FastF1Source(offline=offline)


def get_source(mode=None):
    mode = resolve_mode(mode)
    if mode == "synthetic":
        return SyntheticSource()
    if mode == "openf1":
        return _openf1()
    if mode == "fastf1":
        return _fastf1()
    if has_f1_login() and online("fastf1"):
        return _fastf1()
    return _openf1() if online("openf1") else SyntheticSource()


def _attempts(mode):
    if mode == "openf1":
        return [_openf1]
    if mode == "fastf1":
        return [_fastf1]
    chain = []
    if has_f1_login() and online("fastf1"):
        chain.append(_fastf1)
    if online("openf1"):
        chain.append(_openf1)
    chain.append(lambda: _fastf1(offline=True))
    return chain


def load_with_fallback(key, mode=None, telemetry=True, weather=True):
    mode = resolve_mode(mode)
    if mode == "synthetic":
        return SyntheticSource().load(key, telemetry, weather)
    last = None
    for make in _attempts(mode):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                data = make().load(key, telemetry, weather)
            if len(data.laps):
                return data
        except Exception as exc:
            last = exc
            log.info("load failed for %s: %s", key, exc)
    if mode in {"openf1", "fastf1"}:
        raise RuntimeError(f"Could not load {key.year} {key.gp} {key.session} from {mode}: {last}")
    return SyntheticSource().load(key, telemetry, weather)


def schedule_with_fallback(year, mode=None):
    mode = resolve_mode(mode)
    if mode != "synthetic":
        try:
            source = get_source(mode)
            sched = source.schedule(year)
            if len(sched):
                return sched, source.name
        except Exception as exc:
            if mode in {"openf1", "fastf1"}:
                raise
            log.warning("Schedule fetch failed: %s", exc)
    return SyntheticSource().schedule(year), "synthetic"


__all__ = [
    "DataSource", "SessionData", "SessionKey", "SyntheticSource", "MODES",
    "get_source", "has_f1_login", "load_with_fallback", "normalise_session", "online", "schedule_with_fallback",
]
