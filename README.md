# railcast

A free, always-on delay nowcaster for NJ Transit rail and the MTA subway. It predicts delays 15, 30 and 60 minutes ahead, then scores itself in public every day against a "current delay persists" baseline.

**Status: Week 1 of 10, collector only.** No model or site yet. The plan is in [docs/architecture.md](docs/architecture.md), and choices are logged in [docs/decisions.md](docs/decisions.md).

## How it works (so far)

- Every 5 minutes, a GitHub Actions job in [railcast-data](https://github.com/palism1/railcast-data) runs this package's collector.
- The collector fetches 9 MTA GTFS-realtime feeds (all subway lines plus alerts) and, once credentials are set, NJ Transit rail trip updates and alerts.
- Each run commits three things to the data repo:
  - the exact bytes received (`raw/`)
  - one normalized row per (trip, stop) (`parquet/`)
  - one uptime row per feed, failures included (`logs/uptime/`)
- Static GTFS is downloaded once a day and stored by content hash, so schedule changes show up as new files.

## Run it locally

```bash
uv sync                                   # uv: fast Python env + lockfile manager
uv run pytest                             # fixtures only, no network
uv run railcast-collect --out ../railcast-data --dry-run   # live fetch, writes nothing
uv run python -m railcast.collect.uptime ../railcast-data  # soak report
```

For NJ Transit, set `NJT_USERNAME` and `NJT_PASSWORD` (from developer.njtransit.com RailData access). Without them, the collector runs MTA-only.

## Data terms

MTA data is used under the MTA's developer terms. NJ Transit data is used under NJ Transit's developer agreement. This project is not affiliated with or endorsed by NJ Transit or the MTA. Data may not be real time, accurate, or complete.
