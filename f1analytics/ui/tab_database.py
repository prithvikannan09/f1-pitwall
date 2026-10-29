import streamlit as st

from f1analytics import config
from f1analytics.db.loader import list_sessions, write_session
from f1analytics.db.queries import list_queries, query_sql, run_query
from f1analytics.db.schema import connect, init_db
from f1analytics.ui.state import SESSION_LABELS, get


def render(ctx):
    st.subheader("SQL database")
    st.caption(f"Sessions are stored in a DuckDB file ({config.DB_PATH.name}) with the PostgreSQL-compatible schema from the blueprint.")
    c1, c2 = st.columns([2, 1])
    code = c1.selectbox("Save this session", list(SESSION_LABELS), index=list(SESSION_LABELS).index("R"), format_func=SESSION_LABELS.get, key="db_code")
    if c2.button("Save to database", type="primary", key="db_save"):
        sd = get(ctx, code)
        if sd is not None:
            try:
                con = init_db(connect())
                result = write_session(con, sd)
                con.close()
                st.success("Already saved." if result.get("skipped") else f"Saved {result['laps']} laps and {result['telemetry']} telemetry rows.")
            except Exception as exc:
                st.error(f"Could not save: {exc}")
    try:
        con = init_db(connect())
    except Exception as exc:
        st.error(f"Database is busy or missing: {exc}")
        return
    try:
        stored = list_sessions(con)
        if stored.empty:
            st.info("Nothing stored yet. Click Save, or run: python -m f1analytics setup")
            return
        st.dataframe(stored, hide_index=True)
        sid = st.selectbox("Session to query", stored["session_id"].tolist(), index=len(stored) - 1, key="db_sid")
        name = st.selectbox("Example query", list_queries(), key="db_q")
        st.code(query_sql(name), language="sql")
        st.dataframe(run_query(con, name, session_id=sid), hide_index=True)
    finally:
        con.close()
