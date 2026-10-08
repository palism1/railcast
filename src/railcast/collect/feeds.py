# FILE MAP
#   purpose: the list of real-time and static feeds railcast collects
#   sections:
#     L11-47  Feeds
#     L49-54  Static GTFS
# END FILE MAP
"""Feed registry. One place to add, drop, or re-point a feed."""

from dataclasses import dataclass

# == Feeds ==
MTA_BASE = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/"


@dataclass(frozen=True)
class Feed:
    agency: str  # "mta" | "njt"
    name: str  # short id used in file names and logs
    url: str
    kind: str  # "trip_updates" | "alerts" | "static" (zip, not protobuf)


# TWEAK: drop entries here to shrink storage; names are stable ids in the data repo.
MTA_FEEDS: tuple[Feed, ...] = tuple(
    Feed("mta", name, MTA_BASE + path, kind)
    for name, path, kind in [
        ("mta-1234567s", "nyct%2Fgtfs", "trip_updates"),
        ("mta-ace", "nyct%2Fgtfs-ace", "trip_updates"),
        ("mta-bdfm", "nyct%2Fgtfs-bdfm", "trip_updates"),
        ("mta-g", "nyct%2Fgtfs-g", "trip_updates"),
        ("mta-jz", "nyct%2Fgtfs-jz", "trip_updates"),
        ("mta-nqrw", "nyct%2Fgtfs-nqrw", "trip_updates"),
        ("mta-l", "nyct%2Fgtfs-l", "trip_updates"),
        ("mta-si", "nyct%2Fgtfs-si", "trip_updates"),
        ("mta-alerts", "camsys%2Fsubway-alerts", "alerts"),
    ]
)

# NJ Transit RailData GTFSRT API. Every call is a multipart POST carrying a token.
NJT_BASE = "https://raildata.njtransit.com/api/GTFSRT/"
# CHANGE ME: method names are inferred from open-source clients (only getAlerts is
# confirmed). Check them against the RailData Swagger page once logged in.
NJT_FEEDS: tuple[Feed, ...] = (
    Feed("njt", "njt-rail", NJT_BASE + "getTripUpdates", "trip_updates"),
    Feed("njt", "njt-alerts", NJT_BASE + "getAlerts", "alerts"),
)
NJT_TOKEN_URL = NJT_BASE + "getToken"

# == Static GTFS ==
# Downloaded at most once per UTC day each (NJT allows 5 schedule downloads/day).
MTA_STATIC = Feed(
    "mta", "mta-static", "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip", "static"
)
NJT_STATIC = Feed("njt", "njt-static", NJT_BASE + "getGTFS", "static")  # CHANGE ME: verify name
