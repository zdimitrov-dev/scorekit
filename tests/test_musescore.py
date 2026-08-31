from types import SimpleNamespace

import pytest

from scorekit.connectors import musescore
from scorekit.connectors.base import ConnectorUnavailable
from scorekit.connectors.musescore import MuseScoreConnector, _clean_title, _score_id, _thumbnail


# --- fakes -------------------------------------------------------------------
class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status
        self.calls = 0

    def post(self, url, headers=None, json=None):
        self.calls += 1
        return _Resp(self._payload, self.status)


class _DictCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


CFG = SimpleNamespace(tavily_api_key="tvly-test")

TAVILY_RESP = {
    "results": [
        {
            "title": "Clair de Lune Sheet music for Piano (Solo) | Musescore.com",
            "url": "https://musescore.com/user/scores/6937591",
            "content": "Download and print Clair de Lune …",
            "score": 0.93,
            "images": ["https://musescore.com/thumb.png"],
        },
        {
            "title": "Clair de Lune – Debussy",
            "url": "https://musescore.com/classicman/clair-de-lune-debussy",
            "content": "…",
            "score": 0.71,
        },
    ]
}


def test_score_id():
    assert _score_id("https://musescore.com/user/scores/6937591") == "6937591"
    assert _score_id("https://musescore.com/classicman/clair-de-lune?x=1#f") == \
        "https://musescore.com/classicman/clair-de-lune"


def test_clean_title():
    assert _clean_title("Clair de Lune Sheet music for Piano (Solo) | Musescore.com") == \
        "Clair de Lune Sheet music for Piano (Solo)"


def test_thumbnail_handles_string_and_object():
    assert _thumbnail({"images": ["a"]}) == "a"
    assert _thumbnail({"images": [{"url": "b"}]}) == "b"
    assert _thumbnail({}) is None


def test_search_maps_results(monkeypatch):
    monkeypatch.setattr(musescore, "settings", CFG)
    conn = MuseScoreConnector(client=_FakeClient(TAVILY_RESP), cache=_DictCache())
    cards = conn.search("Clair de Lune", limit=10)

    assert [c.external_id for c in cards] == [
        "6937591",
        "https://musescore.com/classicman/clair-de-lune-debussy",
    ]
    first = cards[0]
    assert first.source == "musescore"
    assert first.kind == "listing"
    assert first.title == "Clair de Lune Sheet music for Piano (Solo)"
    assert first.url == "https://musescore.com/user/scores/6937591"
    assert first.thumbnail_url == "https://musescore.com/thumb.png"
    assert first.metadata["tavily_score"] == 0.93
    assert cards[1].thumbnail_url is None


def test_search_uses_cache(monkeypatch):
    monkeypatch.setattr(musescore, "settings", CFG)
    client = _FakeClient(TAVILY_RESP)
    conn = MuseScoreConnector(client=client, cache=_DictCache())
    conn.search("Clair de Lune")
    conn.search("Clair de Lune")
    assert client.calls == 1   # second query served from cache, no extra spend


def test_disabled_raises_connector_unavailable(monkeypatch):
    monkeypatch.setattr(musescore, "settings", SimpleNamespace(tavily_api_key=""))
    with pytest.raises(ConnectorUnavailable):
        MuseScoreConnector(client=_FakeClient(TAVILY_RESP), cache=_DictCache()).search("x")


@pytest.mark.parametrize("status", [401, 403, 429])
def test_auth_or_quota_error_is_skipped(monkeypatch, status):
    monkeypatch.setattr(musescore, "settings", CFG)
    conn = MuseScoreConnector(client=_FakeClient({}, status=status), cache=_DictCache())
    with pytest.raises(ConnectorUnavailable):
        conn.search("x")


def test_no_results_returns_empty(monkeypatch):
    monkeypatch.setattr(musescore, "settings", CFG)
    conn = MuseScoreConnector(client=_FakeClient({}), cache=_DictCache())
    assert conn.search("nothing here") == []
