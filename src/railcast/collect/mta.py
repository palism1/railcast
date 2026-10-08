# FILE MAP
#   purpose: fetch every MTA subway GTFS-RT feed (no API key needed)
#   sections:
#     L20-29  Collect
# END FILE MAP
"""MTA subway collector. Plain GETs; the API key requirement was dropped in 2024."""

import requests

from railcast.collect.feeds import MTA_FEEDS, Feed
from railcast.collect.fetch import (
    TIMEOUT_S,
    USER_AGENT,
    FetchResult,
    fetch_with_retries,
    parse_into,
)


# == Collect ==
def fetch_feed(feed: Feed, session: requests.Session) -> FetchResult:
    result, _ = fetch_with_retries(feed, lambda: session.get(feed.url, timeout=TIMEOUT_S))
    return parse_into(result) if result.status == "ok" and feed.kind != "static" else result


def collect(session: requests.Session | None = None, feeds=MTA_FEEDS) -> list[FetchResult]:
    session = session or requests.Session()
    session.headers.setdefault("User-Agent", USER_AGENT)
    return [fetch_feed(f, session) for f in feeds]
