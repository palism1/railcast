# Decisions log

One entry per choice that someone might later ask "why?" about. Newest last.

## D1. The 5-minute collector runs in `railcast-data`, not here (2026-10-08)
**Why:** if the workflow lives in the data repo, it pushes with its own `GITHUB_TOKEN`, so no personal access token is needed. Its commits also reset GitHub's 60-day inactivity timer for scheduled workflows. This repo holds only code. The data workflow checks out `main` here on every run.
**Cost:** a bad commit to `main` here breaks collection within 5 minutes. CI must stay green on `main`.

## D2. NJ Transit token is cached and encrypted, with a daily sign-in cap (2026-10-08)
**Why:** RailData allows about 10 sign-ins a day, and a 5-minute job runs 288 times a day. The token is reused until the API rejects it, then refreshed once.
- Sign-ins are capped at 8 per UTC day, and failed attempts count too.
- After one auth failure, the rest of that run doesn't sign in again.
- The cache lives in the Actions cache. That is readable by other workflows in a public repo, so it is Fernet-encrypted with a key derived from `NJT_PASSWORD`, which only secret-bearing runs have.

## D3. All data repo paths use UTC (2026-10-08)
**Why:** no DST gaps or duplicated hours. Service-day logic, which crosses midnight local time, belongs in labeling (Week 2), not in file paths.

## D4. MTA static GTFS uses the regular feed for now (2026-10-08)
`gtfs_supplemented.zip` reflects planned service changes and will matter for delay labels. It changes much more often, though, and is stored by hash, so it could grow the repo fast. That decision is deferred to Week 2, when labels are built.

## D5. Test fixtures are synthetic until the first live run (2026-10-08)
The build sandbox could not reach either feed. `tests/fixtures/make_fixtures.py` builds protobufs shaped like each agency's feed. **TODO:** after the first live collection, copy one real `raw/*.pb.gz` per agency into `tests/fixtures/` and point the tests at it.

## D6. FILE MAP line ranges are generated, not hand-written (2026-10-08)
Hand-maintained line ranges rot on the first edit. Sections are marked `# == Name ==`. `scripts/filemap.py` rewrites the header, and CI fails if one is stale.

## D7. MTA-only until NJ Transit credentials exist (2026-10-08)
NJT feeds log as `skipped` until `NJT_USERNAME` and `NJT_PASSWORD` are set as secrets on `railcast-data`. MTA collection should not wait on NJT's manual approval.
