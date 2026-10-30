import logging
import os
import sys

ENV_USER = "F1_USERNAME"
ENV_PASS = "F1_PASSWORD"
log = logging.getLogger("f1analytics.live")


def has_credentials():
    return bool(os.environ.get(ENV_USER) and os.environ.get(ENV_PASS))


def _stored_token():
    try:
        from fastf1.internals.f1account import token_manager

        token = token_manager.get_stored()
        return token if token is not None and token.is_valid() else None
    except Exception:
        return None


def subscription_token():
    stored = _stored_token()
    if stored is not None:
        return stored.value
    if not has_credentials():
        return None
    try:
        from fastf1.internals.f1account import get_token, set_auth_method

        set_auth_method("password")
        return get_token().value
    except Exception as exc:
        log.warning("F1TV sign-in failed, continuing with free data: %s", exc)
        return None


def status():
    token = _stored_token()
    if token is None:
        return {"signed_in": False, "credentials_set": has_credentials()}
    claims = {}
    try:
        claims = token.claims
    except Exception:
        pass
    return {
        "signed_in": True,
        "credentials_set": has_credentials(),
        "expires_at": token.expires_at,
        "subscription": claims.get("SubscribedProduct") or claims.get("SubscriptionStatus") or claims.get("subscriptionStatus"),
    }


def login_interactive():
    from fastf1.internals.f1account import get_token, set_auth_method

    if not has_credentials() and not sys.stdin.isatty():
        raise RuntimeError("Run this in your own terminal so it can ask for your F1TV email and password.")
    set_auth_method("password")
    get_token(force_renew=True)
    return status()


def load_streamlit_secrets():
    try:
        import streamlit as st

        secrets = st.secrets
        for key in (ENV_USER, ENV_PASS, "PITWALL_KEY"):
            if key in secrets and not os.environ.get(key):
                os.environ[key] = str(secrets[key])
    except Exception:
        pass
