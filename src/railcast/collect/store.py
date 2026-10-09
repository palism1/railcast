# FILE MAP
#   purpose: write raw snapshots, normalized parquet, and the uptime log into the data repo
#   sections:
#     L26-34  Paths
#     L37-120  Write
# END FILE MAP
"""Data repo layout (all paths UTC):

raw/YYYY-MM-DD/HHMM_<feed>.pb.gz     exact bytes we received, gzipped
parquet/YYYY-MM-DD/HHMM.parquet      normalized trip-update rows for the whole run
logs/uptime/YYYY-MM-DD.csv           one row per feed per run, including failures
state/<feed>.sha256                  last stored alerts content, so unchanged alerts are skipped
"""

import csv
import gzip
import hashlib
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from railcast.collect.fetch import FetchResult

# == Paths ==
UPTIME_FIELDS = [
    "run_started_at", "cron_lag_s", "agency", "feed", "status", "http_status",
    "bytes", "latency_ms", "feed_ts", "feed_age_s", "entities", "error", "raw_stored",
]  # fmt: skip


def stamp(run_at: datetime) -> tuple[str, str]:
    return run_at.strftime("%Y-%m-%d"), run_at.strftime("%H%M")


# == Write ==
def content_hash(r: FetchResult) -> str:
    """Hash of the feed with the header timestamp cleared, so a re-stamped but otherwise
    identical alerts feed hashes the same."""
    msg = type(r.message)()
    msg.CopyFrom(r.message)
    msg.header.ClearField("timestamp")
    return hashlib.sha256(msg.SerializeToString(deterministic=True)).hexdigest()


def alerts_unchanged(out: Path, r: FetchResult) -> bool:
    """True if this alerts payload matches the last stored one. Updates state when it differs.
    TWEAK: alerts are ~40% of raw bytes per run and change far less often than every 5 min."""
    if r.feed.kind != "alerts" or r.message is None:
        return False
    state = out / "state" / f"{r.feed.name}.sha256"
    h = content_hash(r)
    if state.exists() and state.read_text().strip() == h:
        return True
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(h + "\n")
    return False


def write_raw(out: Path, run_at: datetime, results: list[FetchResult]) -> list[Path]:
    day, hhmm = stamp(run_at)
    written = []
    for r in results:
        if r.status != "ok" or r.feed.kind == "static" or alerts_unchanged(out, r):
            continue
        p = out / "raw" / day / f"{hhmm}_{r.feed.name}.pb.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        # mtime=0 keeps the gzip bytes deterministic for identical payloads.
        p.write_bytes(gzip.compress(r.content, mtime=0))
        written.append(p)
        r.raw_stored = True
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
                    "raw_stored": int(r.raw_stored),
                }
            )
    return p
