from pathlib import Path

import duckdb

from f1analytics import config


def connect(path=None, read_only=False):
    target = config.DB_PATH if path is None else path
    if str(target) != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(target), read_only=read_only)


def schema_sql():
    return (config.SQL_DIR / "schema.sql").read_text()


def init_db(con):
    for statement in schema_sql().split(";"):
        if statement.strip():
            con.execute(statement)
    return con
