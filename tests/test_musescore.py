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

    def get(self, url, params=None):
        self.calls += 1
        return _Resp(self._payload, self.status)


class _DictCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


CFG = SimpleNamespace(google_cse_id="cx", google_cse_key="key")

CSE_RESP = {
    "items": [
        {
            "title": "Clair de Lune Sheet music for Piano (Solo) | Musescore.com",
            "link": "https://musescore.com/user/scores/6937591",
            "displayLink": "musescore.com",
            "snippet": "Download and print Clair de Lune ...",
            "pagemap": {
                "cse_thumbnail": [{"src": "https://tbn0/thumb.jpg"}],
                "metatags": [{"og:image": "https://musescore.com/og.jpg"}],
            },
        },
        {
            "title": "Clair de Lune – Debussy | Musescore.com",
            "link": "https://musescore.com/classicman/clair-de-lune-debussy",
            "snippet": "...",
            "pagemap": {},
        },
    ]
}


def test_score_id():
    assert _score_id("https://musescore.com/user/scores/6937591") == "6937591"
    # no /scores/<id> -> falls back to the URL without query/fragment
    assert _score_id("https://musescore.com/classicman/clair-de-lune?x=1#f") == \
        "https://musescore.com/classicman/clair-de-lune"


def test_clean_title():
    assert _clean_title("Clair de Lune Sheet music for Piano (Solo) | Musescore.com") == \
        "Clair de Lune Sheet music for Piano (Solo)"


def test_thumbnail_prefers_cse_thumbnail():
    assert _thumbnail({"cse_thumbnail": [{"src": "a"}], "metatags": [{"og:image": "b"}]}) == "a"
    assert _thumbnail({"metatags": [{"og:image": "b"}]}) == "b"
    assert _thumbnail({}) is None


def test_search_maps_results(monkeypatch):
    monkeypatch.setattr(musescore, "settings", CFG)
    conn = MuseScoreConnector(client=_FakeClient(CSE_RESP), cache=_DictCache())
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
    assert first.thumbnail_url == "https://tbn0/thumb.jpg"


def test_search_uses_cache(monkeypatch):
    monkeypatch.setattr(musescore, "settings", CFG)
    client = _FakeClient(CSE_RESP)
    conn = MuseScoreConnector(client=client, cache=_DictCache())
    conn.search("Clair de Lune")
    conn.search("Clair de Lune")
    assert client.calls == 1   # second query served from cache, no extra quota spent


def test_disabled_raises_connector_unavailable(monkeypatch):
    monkeypatch.setattr(musescore, "settings", SimpleNamespace(google_cse_id="", google_cse_key=""))
    with pytest.raises(ConnectorUnavailable):
        MuseScoreConnector(client=_FakeClient(CSE_RESP), cache=_DictCache()).search("x")


def test_quota_exceeded_raises(monkeypatch):
    monkeypatch.setattr(musescore, "settings", CFG)
    conn = MuseScoreConnector(client=_FakeClient({}, status=429), cache=_DictCache())
    with pytest.raises(ConnectorUnavailable):
        conn.search("x")


def test_no_items_returns_empty(monkeypatch):
    monkeypatch.setattr(musescore, "settings", CFG)
    conn = MuseScoreConnector(client=_FakeClient({}), cache=_DictCache())
    assert conn.search("nothing here") == []
