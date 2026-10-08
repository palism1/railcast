# FILE MAP
#   purpose: shared fetch result type and HTTP-with-retries helper
#   sections:
#     L19-37  Result
#     L40-89  Fetch
# END FILE MAP
"""HTTP plumbing shared by the MTA and NJT collectors."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import requests
from google.transit import gtfs_realtime_pb2

from railcast.collect.feeds import Feed

# == Result ==
USER_AGENT = "railcast/0.1 (+https://github.com/palism1/railcast)"
# TWEAK: per-request timeout and retry count. 9 MTA feeds x worst case must fit in a run.
TIMEOUT_S = 20
RETRIES = 2


@dataclass
class FetchResult:
    feed: Feed
    fetched_at: datetime
    status: str  # ok | http_error | network_error | parse_error | skipped
    http_status: int | None = None
    content: bytes = b""
    latency_ms: int = 0
    error: str = ""
    feed_ts: int | None = None  # FeedHeader.timestamp, server-side snapshot time
    entities: int = 0
    message: gtfs_realtime_pb2.FeedMessage | None = field(default=None, repr=False)


# == Fetch ==
def now_utc() -> datetime:
    return datetime.now(UTC)


def parse_into(result: FetchResult) -> FetchResult:
    """Parse protobuf bytes; an HTTP 200 with a garbage body counts as a parse_error."""
    msg = gtfs_realtime_pb2.FeedMessage()
    try:
        msg.ParseFromString(result.content)
    except Exception as exc:  # protobuf raises DecodeError, but be defensive
        result.status, result.error = "parse_error", f"{type(exc).__name__}: {exc}"[:300]
        return result
    if not msg.HasField("header"):
        result.status, result.error = "parse_error", "no FeedHeader"
        return result
    result.message = msg
    result.feed_ts = msg.header.timestamp or None
    result.entities = len(msg.entity)
    return result


def fetch_with_retries(
    feed: Feed,
    do_request: Callable[[], requests.Response],
    no_retry: Callable[[requests.Response], bool] = lambda r: False,
) -> tuple[FetchResult, requests.Response | None]:
    """Run do_request up to RETRIES+1 times. Retries network errors and 5xx, not 4xx,
    and not responses no_retry() flags (e.g. NJT's HTTP 500 "Invalid token")."""
    fetched_at = now_utc()
    last_err, resp = "", None
    for attempt in range(RETRIES + 1):
        t0 = time.monotonic()
        try:
            resp = do_request()
        except requests.RequestException as exc:
            last_err = f"{type(exc).__name__}: {exc}"[:300]
            resp = None
        latency = int((time.monotonic() - t0) * 1000)
        if resp is not None and (resp.status_code < 500 or no_retry(resp)):
            break
        if attempt < RETRIES:
            time.sleep(2**attempt)
    if resp is None:
        return FetchResult(feed, fetched_at, "network_error", error=last_err), None
    result = FetchResult(feed, fetched_at, "ok", resp.status_code, resp.content, latency)
    if resp.status_code != 200:
        result.status = "http_error"
        result.error = resp.text[:300]
    return result, resp
