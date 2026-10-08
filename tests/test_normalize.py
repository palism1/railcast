# FILE MAP
#   purpose: saved protobuf fixtures parse into the exact normalized schema
#   sections:
#     L14-16  Helpers
#     L19-58  Tests
# END FILE MAP
from google.transit import gtfs_realtime_pb2 as rt

from railcast.collect.feeds import MTA_FEEDS, NJT_FEEDS
from railcast.collect.fetch import FetchResult, now_utc, parse_into
from railcast.collect.normalize import SCHEMA, to_table


# == Helpers ==
def parsed(feed, content):
    return parse_into(FetchResult(feed, now_utc(), "ok", 200, content))


# == Tests ==
def test_mta_fixture_matches_schema(mta_bytes):
    t = to_table([parsed(MTA_FEEDS[1], mta_bytes)])
    assert t.schema.equals(SCHEMA)
    assert t.num_rows == 2  # vehicle-only entity ignored
    row = t.to_pylist()[0]
    assert row["agency"] == "mta" and row["feed"] == "mta-ace"
    assert row["trip_id"] == "084600_A..N55R" and row["direction"] == "N"
    assert row["start_date"] == "20261008" and row["stop_id"] == "A41N"
    assert row["arr_time"] == 1791000120 and row["arr_delay"] is None
    assert row["feed_ts"] == 1791000000
    assert row["stop_seq"] is None  # MTA omits stop_sequence; None, not 0


def test_njt_fixture_matches_schema(njt_bytes):
    t = to_table([parsed(NJT_FEEDS[0], njt_bytes)])
    assert t.schema.equals(SCHEMA)
    rows = t.to_pylist()
    assert [r["stop_seq"] for r in rows] == [4, 5, 6, 7]
    assert [r["arr_delay"] for r in rows] == [120, 180, 240, None]
    assert rows[0]["direction"] == "1" and rows[0]["trip_ts"] == 1791000030
    assert rows[-1]["schedule_relationship"] == "SKIPPED"


def test_alerts_and_failures_produce_no_rows(mta_bytes):
    alerts = parsed(MTA_FEEDS[-1], mta_bytes)
    failed = FetchResult(MTA_FEEDS[0], now_utc(), "http_error", 503)
    assert to_table([alerts, failed]).num_rows == 0


def test_garbage_body_is_parse_error():
    r = parsed(MTA_FEEDS[0], b"<html>maintenance</html>")
    assert r.status == "parse_error" and r.message is None


def test_empty_feed_is_valid():
    m = rt.FeedMessage()
    m.header.gtfs_realtime_version = "2.0"
    r = parsed(MTA_FEEDS[0], m.SerializeToString())
    assert r.status == "ok" and r.entities == 0
