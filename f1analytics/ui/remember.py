import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

import streamlit as st

COOKIE = "pw_keep"
TTL_S = 24 * 3600
KEY_FILE = Path(os.environ.get("PITWALL_COOKIE_KEY_FILE", Path.home() / ".cache" / "pitwall_cookie_key"))


def _secret():
    k = os.environ.get("PITWALL_COOKIE_KEY") or os.environ.get("PITWALL_KEY")
    if k:
        return k.encode()
    try:
        if KEY_FILE.exists():
            return KEY_FILE.read_bytes()
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        k = secrets.token_bytes(32)
        KEY_FILE.write_bytes(k)
        return k
    except OSError:
        return _process_secret()


@st.cache_resource
def _process_secret():
    return secrets.token_bytes(32)


def _keys(secret=None):
    s = secret or _secret()
    return hashlib.sha256(b"pw-enc|" + s).digest(), hashlib.sha256(b"pw-mac|" + s).digest()


def _stream(key, nonce, n):
    out = b""
    i = 0
    while len(out) < n:
        out += hashlib.sha256(key + nonce + i.to_bytes(4, "big")).digest()
        i += 1
    return out[:n]


def seal(data, ttl=TTL_S, now=None, secret=None):
    now = now or time.time()
    until = min(now + ttl, data.get("exp") or now + ttl)
    body = json.dumps(dict(data, until=until), separators=(",", ":")).encode()
    ek, mk = _keys(secret)
    nonce = secrets.token_bytes(16)
    ct = bytes(a ^ b for a, b in zip(body, _stream(ek, nonce, len(body))))
    mac = hmac.new(mk, nonce + ct, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + ct + mac).decode().rstrip("="), int(until - now)


def unseal(value, now=None, secret=None):
    if not value:
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError):
        return None
    if len(raw) < 48:
        return None
    nonce, ct, mac = raw[:16], raw[16:-32], raw[-32:]
    ek, mk = _keys(secret)
    if not hmac.compare_digest(mac, hmac.new(mk, nonce + ct, hashlib.sha256).digest()):
        return None
    try:
        data = json.loads(bytes(a ^ b for a, b in zip(ct, _stream(ek, nonce, len(ct)))))
    except ValueError:
        return None
    if (data.get("until") or 0) <= (now or time.time()):
        return None
    return data


def cookie_value():
    try:
        return st.context.cookies.get(COOKIE)
    except Exception:
        return None


def restore():
    if st.session_state.get("pw_restored"):
        return
    st.session_state["pw_restored"] = True
    data = unseal(cookie_value())
    if not data:
        return
    if data.get("token"):
        st.session_state["f1tv_token"], st.session_state["f1tv_exp"] = data["token"], data.get("exp") or data["until"]
    if data.get("owner"):
        st.session_state["pw_owner"] = True


def remember(data):
    st.session_state["pw_cookie"] = seal(data)


def forget():
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
