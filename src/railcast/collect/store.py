# FILE MAP
#   purpose: write raw snapshots, normalized parquet, and the uptime log into the data repo
#   sections:
#     L24-32  Paths
#     L35-93  Write
# END FILE MAP
"""Data repo layout (all paths UTC):

raw/YYYY-MM-DD/HHMM_<feed>.pb.gz     exact bytes we received, gzipped
parquet/YYYY-MM-DD/HHMM.parquet      normalized trip-update rows for the whole run
logs/uptime/YYYY-MM-DD.csv           one row per feed per run, including failures
"""

import csv
import gzip
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from railcast.collect.fetch import FetchResult

# == Paths ==
UPTIME_FIELDS = [
    "run_started_at", "cron_lag_s", "agency", "feed", "status", "http_status",
    "bytes", "latency_ms", "feed_ts", "feed_age_s", "entities", "error",
]  # fmt: skip


def stamp(run_at: datetime) -> tuple[str, str]:
    return run_at.strftime("%Y-%m-%d"), run_at.strftime("%H%M")


# == Write ==
def write_raw(out: Path, run_at: datetime, results: list[FetchResult]) -> list[Path]:
    day, hhmm = stamp(run_at)
    written = []
    for r in results:
        if r.status != "ok" or r.feed.kind == "static":
            continue
        p = out / "raw" / day / f"{hhmm}_{r.feed.name}.pb.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        # mtime=0 keeps the gzip bytes deterministic for identical payloads.
        p.write_bytes(gzip.compress(r.content, mtime=0))
        written.append(p)
    return written


def write_parquet(out: Path, run_at: datetime, table: pa.Table) -> Path | None:
    if table.num_rows == 0:
        return None
    day, hhmm = stamp(run_at)
    p = out / "parquet" / day / f"{hhmm}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, p, compression="zstd")
    return p


def cron_lag_s(run_at: datetime) -> int:
    """Seconds past the 5-minute boundary. Only meaningful under 300; the uptime report
    also measures gaps between consecutive runs, which catches longer delays."""
    return (run_at.minute % 5) * 60 + run_at.second


def append_uptime(out: Path, run_at: datetime, results: list[FetchResult]) -> Path:
    day, _ = stamp(run_at)
    p = out / "logs" / "uptime" / f"{day}.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with p.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=UPTIME_FIELDS)
        if new:
            w.writeheader()
        for r in results:
            age = int(r.fetched_at.timestamp()) - r.feed_ts if r.feed_ts else ""
            w.writerow(
                {
                    "run_started_at": run_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "cron_lag_s": cron_lag_s(run_at),
                    "agency": r.feed.agency,
                    "feed": r.feed.name,
                    "status": r.status,
                    "http_status": r.http_status or "",
                    "bytes": len(r.content),
                    "latency_ms": r.latency_ms,
                    "feed_ts": r.feed_ts or "",
                    "feed_age_s": age,
                    "entities": r.entities,
                    "error": r.error.replace("\n", " ")[:200],
                }
            )
    return p
