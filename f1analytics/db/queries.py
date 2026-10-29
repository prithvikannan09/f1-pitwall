from f1analytics import config

QUERY_DIR = config.SQL_DIR / "queries"


def list_queries():
    return sorted(p.stem for p in QUERY_DIR.glob("*.sql"))


def query_sql(name):
    matches = [p for p in QUERY_DIR.glob("*.sql") if p.stem == name or p.stem.split("_", 1)[-1] == name or p.stem.startswith(f"{name}_")]
    if not matches:
        raise LookupError(f"Unknown query {name!r}; choose from {', '.join(list_queries())}")
    return matches[0].read_text()


def run_query(con, name, **params):
    return con.execute(query_sql(name), params).df()


def latest_session_id(con):
    rows = con.execute("SELECT session_id FROM sessions ORDER BY loaded_at DESC LIMIT 1").fetchall()
    return rows[0][0] if rows else None
