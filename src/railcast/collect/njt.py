# FILE MAP
#   purpose: NJ Transit RailData GTFS-RT collector with an encrypted, budgeted token cache
#   sections:
#     L34-74  Token cache
#     L77-142  Client
#     L145-158  Collect
# END FILE MAP
"""NJ Transit rail collector.

RailData allows about 10 sign-ins per day, so a 5-minute collector cannot sign in on
every run. The token is cached (encrypted) between runs and refreshed only when the
API rejects it, with a hard daily cap below NJT's limit.
"""

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import requests
from cryptography.fernet import Fernet, InvalidToken

from railcast.collect.feeds import NJT_FEEDS, NJT_TOKEN_URL, Feed
from railcast.collect.fetch import (
    TIMEOUT_S,
    USER_AGENT,
    FetchResult,
    fetch_with_retries,
    now_utc,
    parse_into,
)

# == Token cache ==
# DO NOT TOUCH: NJT allows ~10 sign-ins/day; going over can lock the account for the day.
SIGN_IN_BUDGET_PER_DAY = 8


class TokenBudgetExhausted(RuntimeError):
    pass


class NjtAuthError(RuntimeError):
    pass


class TokenCache:
    """JSON {token, sign_ins: {YYYY-MM-DD: n}} encrypted with a key derived from the password.

    The Actions cache is readable by other workflows in a public repo; secrets are not,
    so encrypting with a password-derived key keeps the token private.
    """

    def __init__(self, path: Path, password: str):
        self.path = Path(path)
        key = hashlib.sha256(("railcast-njt-token:" + password).encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(key))
        self.data: dict = {"token": None, "sign_ins": {}}
        if self.path.exists():
            try:
                self.data = json.loads(self._fernet.decrypt(self.path.read_bytes()))
            except (InvalidToken, ValueError):
                pass  # wrong key or corrupt file: start fresh, sign-in budget still applies

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(self._fernet.encrypt(json.dumps(self.data).encode()))

    def sign_ins_today(self, today: str) -> int:
        return int(self.data.get("sign_ins", {}).get(today, 0))

    def record_sign_in(self, token: str, today: str) -> None:
        # Keep only today's counter so the file stays tiny.
        self.data = {"token": token, "sign_ins": {today: self.sign_ins_today(today) + 1}}


# == Client ==
def _is_invalid_token(resp: requests.Response | None) -> bool:
    return resp is not None and resp.status_code >= 400 and "invalid token" in resp.text.lower()


class NjtClient:
    def __init__(
        self,
        username: str,
        password: str,
        cache: TokenCache,
        session: requests.Session | None = None,
        budget: int = SIGN_IN_BUDGET_PER_DAY,
        clock=lambda: datetime.now(UTC),
    ):
        self.username, self.password, self.cache, self.budget = username, password, cache, budget
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.clock = clock
        self.cache_dirty = (
            False  # True when this run changed the cache (new token or sign-in count)
        )
        self.auth_failed = ""  # after one auth failure, later feeds in this run don't sign in again

    def sign_in(self) -> str:
        today = self.clock().strftime("%Y-%m-%d")
        if self.cache.sign_ins_today(today) >= self.budget:
            raise TokenBudgetExhausted(f"{self.budget} sign-ins already used on {today} UTC")
        form = {"username": (None, self.username), "password": (None, self.password)}
        resp = self.session.post(NJT_TOKEN_URL, files=form, timeout=TIMEOUT_S)
        # Count the attempt even if it fails: NJT counts it too.
        try:
            body = resp.json()
        except ValueError:
            body = {}
        token = body.get("UserToken") if str(body.get("Authenticated")) == "True" else None
        self.cache.record_sign_in(token or "", today)
        self.cache_dirty = True
        if not token:
            self.cache.data["token"] = None
            self.cache.save()
            raise NjtAuthError(f"getToken failed (HTTP {resp.status_code})")
        self.cache.save()
        return token

    def _post(self, feed: Feed, token: str):
        return fetch_with_retries(
            feed,
            lambda: self.session.post(feed.url, files={"token": (None, token)}, timeout=TIMEOUT_S),
            no_retry=_is_invalid_token,
        )

    def fetch_feed(self, feed: Feed) -> FetchResult:
        if self.auth_failed:
            return FetchResult(feed, now_utc(), "auth_error", error=self.auth_failed)
        try:
            token = self.cache.data.get("token") or self.sign_in()
            result, resp = self._post(feed, token)
            if _is_invalid_token(resp):
                result, resp = self._post(feed, self.sign_in())
        except (TokenBudgetExhausted, NjtAuthError) as exc:
            self.auth_failed = str(exc)
            return FetchResult(feed, now_utc(), "auth_error", error=self.auth_failed)
        if _is_invalid_token(resp):
            result.status, result.error = "auth_error", "token rejected after refresh"
        return parse_into(result) if result.status == "ok" and feed.kind != "static" else result


# == Collect ==
def make_client(
    username: str | None, password: str | None, cache_path: Path, session=None
) -> NjtClient | None:
    """None without credentials; the runner then logs every NJT feed as 'skipped'."""
    if not username or not password:
        return None
    return NjtClient(username, password, TokenCache(cache_path, password), session)


def collect(client: NjtClient | None, feeds=NJT_FEEDS) -> list[FetchResult]:
    if client is None:
        return [FetchResult(f, now_utc(), "skipped", error="no NJT credentials") for f in feeds]
    return [client.fetch_feed(f) for f in feeds]
