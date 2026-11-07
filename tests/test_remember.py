from f1analytics.ui import remember


def test_save_load_expiry_and_drop():
    sid, max_age = remember.save({"token": "t", "exp": 10_000_000_000}, now=1000)
    assert max_age == remember.TTL_S
    assert remember.load(sid, now=1000 + 3600)["token"] == "t"
    assert remember.load(sid, now=1000 + remember.TTL_S + 1) is None
    sid2, _ = remember.save({"owner": True}, now=1000)
    remember.drop(sid2)
    assert remember.load(sid2, now=1001) is None


def test_keep_never_outlives_f1_token():
    sid, max_age = remember.save({"token": "t", "exp": 1000 + 600}, now=1000)
    assert max_age == 600
    assert remember.load(sid, now=1000 + 601) is None


def test_unknown_or_missing_key():
    assert remember.load(None) is None
    assert remember.load("not-a-real-key") is None


def test_cookie_script_is_scoped_and_expires():
    js = remember.cookie_script("abc", 86400)
    assert "pw_keep=abc" in js and "max-age=86400" in js and "secure" in js and "samesite=strict" in js
    assert "max-age=0" in remember.cookie_script("", 0)
