# FILE MAP
#   purpose: per-feed uptime and cron-gap report from logs/uptime/*.csv
#   sections:
#     L15-27  Load
#     L30-75  Report
# END FILE MAP
"""`python -m railcast.collect.uptime <data repo> [--days N]` prints the soak report."""

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# == Load ==
EXPECTED_GAP_S = 300


def load(data: Path, days: int | None = None) -> list[dict]:
    files = sorted((data / "logs" / "uptime").glob("*.csv"))
    if days:
        files = files[-days:]
    rows = []
    for p in files:
        with p.open(newline="") as f:
            rows += list(csv.DictReader(f))
    return rows


# == Report ==
def percentile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))] if xs else float("nan")


def report(rows: list[dict]) -> dict:
    by_feed: dict[str, list[str]] = defaultdict(list)
    runs: set[str] = set()
    for r in rows:
        runs.add(r["run_started_at"])
        if r["status"] != "skipped":
            by_feed[r["feed"]].append(r["status"])
    times = sorted(datetime.fromisoformat(t.replace("Z", "+00:00")) for t in runs)
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:], strict=False)]
    span_s = (times[-1] - times[0]).total_seconds() if len(times) > 1 else 0
    expected = int(span_s // EXPECTED_GAP_S) + 1 if times else 0
    return {
        "runs": len(times),
        "expected_runs": expected,
        "run_coverage": len(times) / expected if expected else float("nan"),
        "span_h": span_s / 3600,
        "gap_p50_s": percentile(gaps, 0.5),
        "gap_p95_s": percentile(gaps, 0.95),
        "gap_max_s": max(gaps, default=float("nan")),
        "feeds": {f: sum(s == "ok" for s in st) / len(st) for f, st in sorted(by_feed.items())},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("--days", type=int)
    rep = report(load(**vars(ap.parse_args(argv))))
    print(
        f"span {rep['span_h']:.1f}h, runs {rep['runs']}/{rep['expected_runs']} "
        f"({rep['run_coverage']:.1%}), gap p50 {rep['gap_p50_s']:.0f}s "
        f"p95 {rep['gap_p95_s']:.0f}s max {rep['gap_max_s']:.0f}s"
    )
    for feed, up in rep["feeds"].items():
        print(f"  {feed:14s} {up:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
