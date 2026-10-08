# Architecture

Week 1 scope: collection only. The full 10-week design (model, scoring, site, drift) is in the project plan. This file grows as each piece lands.

```
railcast-data/.github/workflows/collect.yml   (cron */5, plus manual dispatch)
  ├─ checkout railcast-data
  ├─ checkout palism1/railcast@main  → uv sync
  ├─ restore NJT token cache (encrypted, actions/cache)
  ├─ railcast-collect --out .
  │    mta.collect()      9 GETs, no key
  │    njt.collect()      2 POSTs with cached token (skipped without creds)
  │    gtfs_static.update once per UTC day per agency, dedup by sha256
  │    normalize.to_table one row per (trip, stop_time_update)
  │    store.*            raw/, parquet/, logs/uptime/
  ├─ save token cache if it changed
  └─ commit + push (rebase and retry on conflict)
```

| Module | Job |
|---|---|
| `collect/feeds.py` | Every URL in one place |
| `collect/fetch.py` | Retries (network errors and 5xx), protobuf parsing, `FetchResult` |
| `collect/mta.py` / `njt.py` | Agency collectors; NJT owns the token logic |
| `collect/normalize.py` | The shared schema (`SCHEMA`) |
| `collect/gtfs_static.py` | Daily static zips plus `static/manifest.csv` |
| `collect/store.py` | Data repo layout |
| `collect/uptime.py` | Soak report: per-feed uptime and gaps between runs |
