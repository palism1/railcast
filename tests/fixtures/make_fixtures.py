# FILE MAP
#   purpose: build the synthetic GTFS-RT fixtures used by tests (rerun to regenerate)
#   sections:
#     L17-52  Builders
#     L55-59  Write
# END FILE MAP
"""Synthetic fixtures shaped like each agency's feed. Replace with real captures from the
first live collector run (see docs/decisions.md, D5); the tests should still pass."""

from pathlib import Path

from google.transit import gtfs_realtime_pb2 as rt

HERE = Path(__file__).parent


# == Builders ==
def mta() -> rt.FeedMessage:
    m = rt.FeedMessage()
    m.header.gtfs_realtime_version = "1.0"
    m.header.timestamp = 1791000000
    e = m.entity.add(id="000001A")
    e.trip_update.trip.trip_id = "084600_A..N55R"
    e.trip_update.trip.start_date = "20261008"
    e.trip_update.trip.route_id = "A"
    s1 = e.trip_update.stop_time_update.add(stop_id="A41N")
    s1.arrival.time = 1791000120
    s1.departure.time = 1791000150
    s2 = e.trip_update.stop_time_update.add(stop_id="A40N")
    s2.arrival.time = 1791000300
    # Vehicle-only entity: must be ignored by the trip-update normalizer.
    v = m.entity.add(id="000002A")
    v.vehicle.trip.trip_id = "084600_A..N55R"
    v.vehicle.current_stop_sequence = 3
    return m


def njt() -> rt.FeedMessage:
    m = rt.FeedMessage()
    m.header.gtfs_realtime_version = "2.0"
    m.header.timestamp = 1791000060
    e = m.entity.add(id="3881")
    t = e.trip_update.trip
    t.trip_id, t.start_date, t.route_id, t.direction_id = "3881", "20261008", "NEC", 1
    e.trip_update.timestamp = 1791000030
    for seq, (stop, delay) in enumerate([("105", 120), ("107", 180), ("148", 240)], start=4):
        s = e.trip_update.stop_time_update.add(stop_id=stop, stop_sequence=seq)
        s.arrival.time, s.arrival.delay = 1791000000 + seq * 600, delay
        s.departure.time, s.departure.delay = 1791000030 + seq * 600, delay
    skipped = e.trip_update.stop_time_update.add(stop_id="38174", stop_sequence=7)
    skipped.schedule_relationship = rt.TripUpdate.StopTimeUpdate.SKIPPED
    return m


# == Write ==
if __name__ == "__main__":
    (HERE / "mta_trip_updates.pb").write_bytes(mta().SerializeToString())
    (HERE / "njt_trip_updates.pb").write_bytes(njt().SerializeToString())
    print("wrote fixtures")
