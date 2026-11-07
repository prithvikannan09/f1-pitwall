import secrets
import threading
import time

import streamlit as st

COOKIE = "pw_keep"
TTL_S = 24 * 3600


@st.cache_resource
def _store():
    return {"lock": threading.Lock(), "items": {}}


def save(data, ttl=TTL_S, now=None):
    now = now or time.time()
    keep_until = min(now + ttl, data.get("exp") or now + ttl)
    sid = secrets.token_urlsafe(32)
    s = _store()
    with s["lock"]:
        for k in [k for k, (until, _) in s["items"].items() if until <= now]:
            s["items"].pop(k, None)
        s["items"][sid] = (keep_until, dict(data))
    return sid, int(keep_until - now)


def load(sid, now=None):
    if not sid:
        return None
    now = now or time.time()
    s = _store()
    with s["lock"]:
        item = s["items"].get(sid)
        if not item:
            return None
        until, data = item
        if until <= now:
            s["items"].pop(sid, None)
            return None
        return dict(data)


def drop(sid):
    if sid:
        s = _store()
        with s["lock"]:
            s["items"].pop(sid, None)


def cookie_sid():
    try:
        return st.context.cookies.get(COOKIE)
    except Exception:
        return None


def restore():
    if st.session_state.get("pw_restored"):
        return
    st.session_state["pw_restored"] = True
    data = load(cookie_sid())
    if not data:
        return
    if data.get("token"):
        st.session_state["f1tv_token"], st.session_state["f1tv_exp"] = data["token"], data.get("exp") or 0
    if data.get("owner"):
        st.session_state["pw_owner"] = True


def remember(data):
    drop(cookie_sid())
    sid, max_age = save(data)
    st.session_state["pw_cookie"] = (sid, max_age)


def forget():
    drop(cookie_sid())
    st.session_state["pw_cookie"] = ("", 0)


def cookie_script(value, max_age):
    return ("<script>try{window.parent.document.cookie='" + COOKIE + "=" + value +
            "; max-age=" + str(int(max_age)) + "; path=/; secure; samesite=strict';}catch(e){}</script>")


def flush_cookie():
    pending = st.session_state.pop("pw_cookie", None)
    if pending is None:
        return
    import streamlit.components.v1 as components

    components.html(cookie_script(*pending), height=0)
