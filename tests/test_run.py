# FILE MAP
#   purpose: end-to-end collector run against fake feeds: layout, uptime log, dry run, static
#   sections:
#     L22-36  Helpers
#     L39-79  Tests
# END FILE MAP
import csv
import io
import zipfile
from datetime import UTC, datetime

import pyarrow.parquet as pq
from conftest import FakeResponse, FakeSession

from railcast.collect import run as runner
from railcast.collect import uptime
from railcast.collect.feeds import MTA_FEEDS, MTA_STATIC

RUN_AT = datetime(2026, 10, 8, 13, 6, 42, tzinfo=UTC)


# == Helpers ==
def zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("stops.txt", "stop_id\nA41N\n")
    return buf.getvalue()


def session(mta_bytes, down=()):
    routes = {f.url: FakeResponse(content=mta_bytes) for f in MTA_FEEDS}
    for name in down:
        url = next(f.url for f in MTA_FEEDS if f.name == name)
        routes[url] = FakeResponse(503, b"down")
    routes[MTA_STATIC.url] = FakeResponse(content=zip_bytes())
    return FakeSession(routes)


# == Tests ==
def test_run_writes_expected_layout(tmp_path, mta_bytes, monkeypatch):
    monkeypatch.delenv("NJT_USERNAME", raising=False)
    s = runner.run(tmp_path, tmp_path / "c.bin", RUN_AT, session(mta_bytes, down=["mta-g"]))
    assert s["feeds_ok"] == 8 and s["feeds_attempted"] == 9 and not s["all_failed"]
    assert (tmp_path / "raw/2026-10-08/1306_mta-ace.pb.gz").exists()
    assert not (tmp_path / "raw/2026-10-08/1306_mta-g.pb.gz").exists()
    t = pq.read_table(tmp_path / "parquet/2026-10-08/1306.parquet")
    assert t.num_rows == 2 * 7  # 7 ok trip-update feeds x 2 rows (alerts feed adds none)

    with open(tmp_path / "logs/uptime/2026-10-08.csv") as f:
        rows = list(csv.DictReader(f))
    by = {r["feed"]: r for r in rows}
    assert by["mta-g"]["status"] == "http_error" and by["mta-g"]["http_status"] == "503"
    assert by["njt-rail"]["status"] == "skipped"
    assert by["mta-ace"]["cron_lag_s"] == str(60 + 42)

    assert s["static"][0]["is_new_version"] is True
    # Same day again: static is not re-downloaded.
    s2 = runner.run(tmp_path, tmp_path / "c.bin", RUN_AT, session(mta_bytes))
    assert s2["static"] == []


def test_dry_run_writes_nothing(tmp_path, mta_bytes, monkeypatch):
    monkeypatch.setattr(runner.requests, "Session", lambda: session(mta_bytes))
    monkeypatch.delenv("NJT_USERNAME", raising=False)
    assert runner.main(["--out", str(tmp_path), "--dry-run"]) == 0
    assert list(tmp_path.iterdir()) == []


def test_uptime_report_counts_gaps(tmp_path):
    p = tmp_path / "logs/uptime"
    p.mkdir(parents=True)
    times = ["2026-10-08T00:00:10Z", "2026-10-08T00:05:20Z", "2026-10-08T00:20:00Z"]
    lines = ["run_started_at,feed,status"]
    lines += [f"{t},mta-ace,ok" for t in times] + [f"{times[1]},mta-g,http_error"]
    (p / "2026-10-08.csv").write_text("\n".join(lines) + "\n")
    rep = uptime.report(uptime.load(tmp_path))
    assert rep["runs"] == 3 and rep["expected_runs"] == 4
    assert rep["gap_max_s"] == 880
    assert rep["feeds"] == {"mta-ace": 1.0, "mta-g": 0.0}
