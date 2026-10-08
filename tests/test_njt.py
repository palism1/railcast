# FILE MAP
#   purpose: NJT token cache: reuse, refresh on rejection, daily sign-in budget, encryption
#   sections:
#     L20-28  Helpers
#     L31-76  Tests
# END FILE MAP
from datetime import UTC, datetime

from conftest import FakeResponse, FakeSession

from railcast.collect import njt
from railcast.collect.feeds import NJT_FEEDS, NJT_TOKEN_URL

FEED = NJT_FEEDS[0]
DAY = datetime(2026, 10, 8, 12, tzinfo=UTC)
TOKEN_OK = FakeResponse(payload={"Authenticated": "True", "UserToken": "tok-new"})
INVALID = FakeResponse(500, payload={"errorMessage": "Invalid token."})


# == Helpers ==
def client(tmp_path, routes, token=None, sign_ins=0, password="pw"):
    cache = njt.TokenCache(tmp_path / "t.bin", password)
    cache.data = {"token": token, "sign_ins": {"2026-10-08": sign_ins}}
    return njt.NjtClient("u", password, cache, FakeSession(routes), clock=lambda: DAY)


def token_sent(call):
    return call[2]["files"]["token"][1]


# == Tests ==
def test_cached_token_is_reused_without_sign_in(tmp_path, njt_bytes):
    c = client(tmp_path, {FEED.url: FakeResponse(content=njt_bytes)}, token="tok-old")
    r = c.fetch_feed(FEED)
    assert r.status == "ok" and r.entities == 1
    assert [u for _, u, _ in c.session.calls] == [FEED.url]
    assert token_sent(c.session.calls[0]) == "tok-old" and not c.cache_dirty


def test_invalid_token_refreshes_once_and_retries(tmp_path, njt_bytes):
    routes = {FEED.url: [INVALID, FakeResponse(content=njt_bytes)], NJT_TOKEN_URL: TOKEN_OK}
    c = client(tmp_path, routes, token="tok-old")
    assert c.fetch_feed(FEED).status == "ok"
    assert token_sent(c.session.calls[-1]) == "tok-new"
    assert c.cache.data == {"token": "tok-new", "sign_ins": {"2026-10-08": 1}}
    assert c.cache_dirty
    # Persisted encrypted, and readable only with the same password.
    assert b"tok-new" not in (tmp_path / "t.bin").read_bytes()
    assert njt.TokenCache(tmp_path / "t.bin", "pw").data["token"] == "tok-new"
    assert njt.TokenCache(tmp_path / "t.bin", "other").data["token"] is None


def test_budget_exhausted_never_calls_get_token(tmp_path):
    c = client(tmp_path, {}, token=None, sign_ins=njt.SIGN_IN_BUDGET_PER_DAY)
    r = c.fetch_feed(FEED)
    assert r.status == "auth_error" and "sign-ins already used" in r.error
    assert c.session.calls == []


def test_bad_credentials_stop_further_sign_ins_this_run(tmp_path):
    bad = FakeResponse(payload={"Authenticated": "False"})
    c = client(tmp_path, {NJT_TOKEN_URL: bad})
    results = [c.fetch_feed(f) for f in NJT_FEEDS]
    assert [r.status for r in results] == ["auth_error", "auth_error"]
    assert sum(u == NJT_TOKEN_URL for _, u, _ in c.session.calls) == 1
    assert c.cache.sign_ins_today("2026-10-08") == 1 and c.cache_dirty  # attempt counted


def test_rejected_after_refresh_is_auth_error(tmp_path):
    c = client(tmp_path, {FEED.url: [INVALID, INVALID], NJT_TOKEN_URL: TOKEN_OK}, token="old")
    assert c.fetch_feed(FEED).status == "auth_error"


def test_no_credentials_means_skipped(tmp_path):
    assert njt.make_client(None, None, tmp_path / "t.bin") is None
    assert {r.status for r in njt.collect(None)} == {"skipped"}
