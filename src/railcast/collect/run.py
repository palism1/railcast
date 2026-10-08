# FILE MAP
#   purpose: one collector run: fetch all feeds, write to the data repo (or dry-run), report
#   sections:
#     L28-60  Run
#     L63-112  CLI
# END FILE MAP
"""Entry point for the 5-minute job: `railcast-collect --out <data repo> [--dry-run]`.

Reads NJT_USERNAME / NJT_PASSWORD from the environment. Without them, NJT feeds are
logged as skipped and MTA collection proceeds (MTA-only mode).
"""

import argparse
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import requests

from railcast.collect import gtfs_static, mta, njt, normalize, store
from railcast.collect.feeds import MTA_STATIC, NJT_STATIC
from railcast.collect.fetch import FetchResult, now_utc


# == Run ==
def run(out: Path, njt_cache: Path, run_at: datetime | None = None, session=None) -> dict:
    run_at = run_at or now_utc()
    session = session or requests.Session()
    client = njt.make_client(
        os.environ.get("NJT_USERNAME"), os.environ.get("NJT_PASSWORD"), njt_cache, session
    )
    results: list[FetchResult] = mta.collect(session) + njt.collect(client)

    day = run_at.strftime("%Y-%m-%d")
    static_rows = [gtfs_static.update(out, MTA_STATIC, day, lambda f: mta.fetch_feed(f, session))]
    if client is not None:
        static_rows.append(gtfs_static.update(out, NJT_STATIC, day, client.fetch_feed))

    table = normalize.to_table(results)
    raw = store.write_raw(out, run_at, results)
    pq_path = store.write_parquet(out, run_at, table)
    store.append_uptime(out, run_at, results)

    ok = [r for r in results if r.status == "ok"]
    attempted = [r for r in results if r.status != "skipped"]
    return {
        "run_at": run_at.isoformat(),
        "feeds_ok": len(ok),
        "feeds_attempted": len(attempted),
        "all_failed": bool(attempted) and not ok,
        "rows": table.num_rows,
        "raw_bytes": sum(p.stat().st_size for p in raw),
        "parquet_bytes": pq_path.stat().st_size if pq_path else 0,
        "static": [r for r in static_rows if r],
        "njt_cache_changed": bool(client and client.cache_dirty),
        "failures": [f"{r.feed.name}: {r.status} {r.error}" for r in attempted if r.status != "ok"],
    }


# == CLI ==
def _summary(s: dict, out: Path) -> str:
    lines = [
        f"run_at={s['run_at']} feeds_ok={s['feeds_ok']}/{s['feeds_attempted']} rows={s['rows']}",
        f"raw_bytes={s['raw_bytes']} parquet_bytes={s['parquet_bytes']}",
        *[
            f"static {r['agency']}: {r['status']} {r['bytes']}B new={r['is_new_version']}"
            for r in s["static"]
        ],
        *[f"FAIL {f}" for f in s["failures"]],
    ]
    files = sorted(p for p in out.rglob("*") if p.is_file() and ".git" not in p.parts)
    lines += [f"  {p.relative_to(out)}  {p.stat().st_size}B" for p in files[-40:]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True, help="data repo checkout")
    ap.add_argument("--njt-cache", type=Path, default=Path(".njt-cache/token.bin"))
    ap.add_argument("--dry-run", action="store_true", help="write to a temp dir and discard")
    args = ap.parse_args(argv)

    if args.dry_run:
        tmp = Path(tempfile.mkdtemp(prefix="railcast-dry-"))
        # Seed the manifest so the dry run makes the same skip decisions as a real run.
        src = args.out / gtfs_static.MANIFEST
        if src.exists():
            (tmp / gtfs_static.MANIFEST).parent.mkdir(parents=True)
            shutil.copy(src, tmp / gtfs_static.MANIFEST)
        target = tmp
    else:
        target = args.out
    s = run(target, args.njt_cache)
    print(
        ("DRY RUN, nothing written to the data repo\n" if args.dry_run else "")
        + _summary(s, target)
    )
    if args.dry_run:
        shutil.rmtree(target)

    if gh := os.environ.get("GITHUB_OUTPUT"):
        with open(gh, "a") as f:
            f.write(f"njt_cache_changed={str(s['njt_cache_changed']).lower()}\n")
            f.write(f"all_failed={str(s['all_failed']).lower()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
