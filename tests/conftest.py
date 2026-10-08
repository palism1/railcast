# FILE MAP
#   purpose: shared fakes: an HTTP session that replays canned responses by URL
#   sections:
#     L15-45  Fakes
#     L48-61  Fixtures
# END FILE MAP
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


# == Fakes ==
class FakeResponse:
    def __init__(self, status_code=200, content=b"", payload=None):
        self.status_code = status_code
        self.content = json.dumps(payload).encode() if payload is not None else content
        self.text = self.content.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.content)


class FakeSession:
    """routes: url -> FakeResponse or list of FakeResponses (consumed in order)."""

    def __init__(self, routes=None, default=None):
        self.routes, self.default, self.calls, self.headers = routes or {}, default, [], {}

    def _answer(self, method, url, **kw):
        self.calls.append((method, url, kw))
        r = self.routes.get(url, self.default)
        if isinstance(r, list):
            r = r.pop(0)
        if r is None:
            raise AssertionError(f"unexpected {method} {url}")
        return r

    def get(self, url, **kw):
        return self._answer("GET", url, **kw)

    def post(self, url, **kw):
        return self._answer("POST", url, **kw)


# == Fixtures ==
@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr("railcast.collect.fetch.time.sleep", lambda s: None)


@pytest.fixture
def mta_bytes() -> bytes:
    return (FIXTURES / "mta_trip_updates.pb").read_bytes()


@pytest.fixture
def njt_bytes() -> bytes:
    return (FIXTURES / "njt_trip_updates.pb").read_bytes()
