import os

import pytest

os.environ["F1_SOURCE"] = "synthetic"
os.environ.setdefault("F1_REPLAY_GPS", "0")

from f1analytics.db.loader import write_session
from f1analytics.db.schema import connect, init_db
from f1analytics.sources import SessionKey, SyntheticSource


@pytest.fixture(scope="session")
def source():
    return SyntheticSource()


@pytest.fixture(scope="session")
def synthetic_race(source):
    return source.load(SessionKey(2024, "Mexico", "R"))


@pytest.fixture(scope="session")
def synthetic_quali(source):
    return source.load(SessionKey(2024, "Mexico", "Q"))


@pytest.fixture(scope="session")
def synthetic_fp2(source):
    return source.load(SessionKey(2024, "Mexico", "FP2"))


@pytest.fixture()
def db(synthetic_race, synthetic_quali, synthetic_fp2):
    con = init_db(connect(":memory:"))
    for sd in (synthetic_fp2, synthetic_quali, synthetic_race):
        write_session(con, sd)
    yield con
    con.close()
