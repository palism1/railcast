# FILE MAP
#   purpose: daily static GTFS download, stored by content hash so version changes are visible
#   sections:
#     L17-44  Manifest
#     L47-72  Update
# END FILE MAP
"""Static GTFS: once per UTC day per agency, dedup by sha256, log every check in a manifest."""

import csv
import hashlib
from collections.abc import Callable
from pathlib import Path

from railcast.collect.feeds import Feed
from railcast.collect.fetch import FetchResult

# == Manifest ==
MANIFEST = Path("static/manifest.csv")
FIELDS = ["date", "agency", "status", "sha256", "bytes", "path", "is_new_version", "error"]


def _read(out: Path) -> list[dict]:
    p = out / MANIFEST
    if not p.exists():
        return []
    with p.open(newline="") as f:
        return list(csv.DictReader(f))


def already_checked(out: Path, agency: str, date: str) -> bool:
    return any(
        r["date"] == date and r["agency"] == agency and r["status"] == "ok" for r in _read(out)
    )


def _append(out: Path, row: dict) -> None:
    p = out / MANIFEST
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with p.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


# == Update ==
def update(out: Path, feed: Feed, date: str, fetch: Callable[[Feed], FetchResult]) -> dict | None:
    """Fetch feed's zip unless already done today. Returns the manifest row, or None if skipped."""
    if already_checked(out, feed.agency, date):
        return None
    res = fetch(feed)
    row = {k: "" for k in FIELDS} | {"date": date, "agency": feed.agency, "status": res.status}
    if res.status == "ok" and not res.content.startswith(b"PK"):
        row |= {"status": "parse_error", "error": "not a zip file"}
    elif res.status == "ok":
        sha = hashlib.sha256(res.content).hexdigest()
        rel = Path("static") / feed.agency / f"{sha[:16]}.zip"
        is_new = not (out / rel).exists()
        if is_new:
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_bytes(res.content)
        row |= {
            "sha256": sha,
            "bytes": len(res.content),
            "path": str(rel),
            "is_new_version": is_new,
        }
    else:
        row["error"] = res.error[:200]
    _append(out, row)
    return row
