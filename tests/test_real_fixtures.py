# FILE MAP
#   purpose: real captured feeds (not synthetic) parse cleanly into the normalized schema
#   sections:
#     L19-32  Tests
# END FILE MAP
"""Real snapshot committed by the collector at 2026-10-08 23:56 UTC (decisions.md D5)."""

import gzip

from conftest import FIXTURES

from railcast.collect.feeds import MTA_FEEDS
from railcast.collect.fetch import FetchResult, now_utc, parse_into
from railcast.collect.normalize import SCHEMA, to_table

SIR = next(f for f in MTA_FEEDS if f.name == "mta-si")


# == Tests ==
def test_real_mta_sir_snapshot():
    raw = gzip.decompress((FIXTURES / "real_mta_si_20261008T2356Z.pb.gz").read_bytes())
    r = parse_into(FetchResult(SIR, now_utc(), "ok", 200, raw))
    assert r.status == "ok" and r.feed_ts == 1791503780 and r.entities == 26
    t = to_table([r])
    assert t.schema.equals(SCHEMA)
    assert t.num_rows == 175  # 13 trip updates, 175 stop_time_updates
    rows = t.to_pylist()
    assert {row["route_id"] for row in rows} == {"SI", "SS"}  # the SIR feed carries two route ids
    # SIR trip ids use a single dot ("115100_SI.N03R"); direction must still parse.
    assert {row["direction"] for row in rows} <= {"N", "S"}
    assert all(row["start_date"] == "20261008" for row in rows)
    assert all(row["arr_time"] or row["dep_time"] for row in rows)
