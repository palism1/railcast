# FILE MAP
#   purpose: flatten GTFS-RT trip updates from both agencies into one row-per-stop schema
#   sections:
#     L17-39  Schema
#     L41-62  Helpers
#     L65-110  Normalize
# END FILE MAP
"""One schema for both agencies: one row per (snapshot, trip, stop_time_update)."""

import re

import pyarrow as pa
from google.transit import gtfs_realtime_pb2

from railcast.collect.fetch import FetchResult

# == Schema ==
# DO NOT TOUCH: downstream labeling and features read these names; add columns, never rename.
SCHEMA = pa.schema(
    [
        ("agency", pa.string()),
        ("feed", pa.string()),
        ("fetched_at", pa.timestamp("s", tz="UTC")),  # when we fetched, not when cron fired
        ("feed_ts", pa.int64()),  # FeedHeader.timestamp (epoch s)
        ("entity_id", pa.string()),
        ("trip_id", pa.string()),
        ("start_date", pa.string()),  # YYYYMMDD; needed to match MTA trips to static GTFS
        ("route_id", pa.string()),
        ("direction", pa.string()),  # "0"/"1" from direction_id, or "N"/"S" from MTA trip_id
        ("trip_ts", pa.int64()),  # TripUpdate.timestamp, when the vehicle last reported
        ("stop_id", pa.string()),
        ("stop_seq", pa.int32()),
        ("arr_time", pa.int64()),
        ("arr_delay", pa.int32()),  # seconds; often absent in MTA feeds (labels come in Week 2)
        ("dep_time", pa.int64()),
        ("dep_delay", pa.int32()),
        ("schedule_relationship", pa.string()),
    ]
)

# == Helpers ==
_MTA_DIR = re.compile(r"\.+([NS])")
_STU = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate


def _opt(msg, name):
    return getattr(msg, name) if msg.HasField(name) else None


def _event(stu, name):
    if not stu.HasField(name):
        return None, None
    ev = getattr(stu, name)
    return _opt(ev, "time"), _opt(ev, "delay")


def _direction(agency: str, trip) -> str | None:
    if trip.HasField("direction_id"):
        return str(trip.direction_id)
    if agency == "mta" and (m := _MTA_DIR.search(trip.trip_id)):
        return m.group(1)
    return None


# == Normalize ==
def rows_from_result(result: FetchResult) -> list[dict]:
    if result.message is None or result.feed.kind != "trip_updates":
        return []
    fetched = result.fetched_at.replace(microsecond=0)
    rows = []
    for ent in result.message.entity:
        if not ent.HasField("trip_update"):
            continue
        tu = ent.trip_update
        trip = tu.trip
        base = {
            "agency": result.feed.agency,
            "feed": result.feed.name,
            "fetched_at": fetched,
            "feed_ts": result.feed_ts,
            "entity_id": ent.id,
            "trip_id": trip.trip_id or None,
            "start_date": trip.start_date or None,
            "route_id": trip.route_id or None,
            "direction": _direction(result.feed.agency, trip),
            "trip_ts": _opt(tu, "timestamp"),
        }
        for stu in tu.stop_time_update:
            arr_t, arr_d = _event(stu, "arrival")
            dep_t, dep_d = _event(stu, "departure")
            rows.append(
                base
                | {
                    "stop_id": stu.stop_id or None,
                    "stop_seq": _opt(stu, "stop_sequence"),
                    "arr_time": arr_t,
                    "arr_delay": arr_d,
                    "dep_time": dep_t,
                    "dep_delay": dep_d,
                    "schedule_relationship": _STU.ScheduleRelationship.Name(
                        stu.schedule_relationship
                    ),
                }
            )
    return rows


def to_table(results: list[FetchResult]) -> pa.Table:
    rows = [r for res in results for r in rows_from_result(res)]
    return pa.Table.from_pylist(rows, schema=SCHEMA)
