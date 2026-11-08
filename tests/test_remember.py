from f1analytics.ui import remember

K = b"test-secret"


def test_seal_roundtrip_survives_restart_and_expires():
    value, max_age = remember.seal({"token": "abc", "exp": 10_000_000_000}, now=1000, secret=K)
    assert max_age == remember.TTL_S
    got = remember.unseal(value, now=1000 + 3600, secret=K)
    assert got["token"] == "abc"
    assert remember.unseal(value, now=1000 + remember.TTL_S + 1, secret=K) is None


def test_never_outlives_f1_token():
    value, max_age = remember.seal({"token": "t", "exp": 1600}, now=1000, secret=K)
    assert max_age == 600
    assert remember.unseal(value, now=1601, secret=K) is None


def test_tampered_or_foreign_cookie_rejected():
    value, _ = remember.seal({"owner": True}, now=1000, secret=K)
    assert remember.unseal(value, now=1001, secret=b"other-secret") is None
    flipped = value[:-3] + ("A" if value[-3] != "A" else "B") + value[-2:]
    assert remember.unseal(flipped, now=1001, secret=K) is None
    assert remember.unseal("garbage", secret=K) is None
    assert remember.unseal(None, secret=K) is None


def test_token_not_readable_in_cookie():
    value, _ = remember.seal({"token": "SECRET-F1TV-TOKEN"}, now=1000, secret=K)
    assert "SECRET" not in value


def test_cookie_script_is_scoped_and_expires():
    js = remember.cookie_script("abc", 86400)
    assert "pw_keep=abc" in js and "max-age=86400" in js and "secure" in js and "samesite=strict" in js
    assert "max-age=0" in remember.cookie_script("", 0)
