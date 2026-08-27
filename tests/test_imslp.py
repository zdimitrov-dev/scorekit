from types import SimpleNamespace

import pytest

from scorekit.connectors import imslp
from scorekit.connectors.base import ConnectorUnavailable
from scorekit.connectors.imslp import (
    ImslpConnector,
    _parse_title,
    _strip_html,
    _work_url,
)


# --- a minimal stand-in for httpx.Client.get(...).json() ---------------------
class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return _FakeResp(self._payload)


SEARCH_PAYLOAD = {
    "query": {
        "search": [
            {"title": "Clair de lune (Debussy, Claude)", "pageid": 12345,
             "snippet": 'from <span class="searchmatch">Suite</span> bergamasque'},
            {"title": "6 Gymnopédies (Satie, Erik)", "pageid": 222, "snippet": ""},
            {"title": "IMSLP:Featured scores", "pageid": 9, "snippet": "meta page"},
        ]
    }
}


def test_parse_title_composer():
    assert _parse_title("Clair de lune (Debussy, Claude)") == ("Clair de lune", "Claude Debussy")
    assert _parse_title("6 Gymnopédies (Satie, Erik)") == ("6 Gymnopédies", "Erik Satie")


def test_parse_title_no_convention():
    assert _parse_title("Some Freeform Page") == ("Some Freeform Page", None)


def test_work_url():
    assert _work_url("Clair de lune (Debussy, Claude)") == \
        "https://imslp.org/wiki/Clair_de_lune_(Debussy,_Claude)"


def test_strip_html():
    assert _strip_html('a <span class="searchmatch">b</span> c') == "a b c"
    assert _strip_html("") == ""


def test_search_maps_results(monkeypatch):
    monkeypatch.setattr(imslp, "settings", SimpleNamespace(imslp_enabled=True))
    conn = ImslpConnector(client=_FakeClient(SEARCH_PAYLOAD))
    cards = conn.search("clair de lune", limit=10)

    assert [c.external_id for c in cards] == ["12345", "222", "9"]

    first = cards[0]
    assert first.source == "imslp"
    assert first.kind == "score"
    assert first.title == "Clair de lune"
    assert first.author == "Claude Debussy"
    assert first.url == "https://imslp.org/wiki/Clair_de_lune_(Debussy,_Claude)"
    assert first.metadata["pageid"] == 12345
    assert first.metadata["snippet"] == "from Suite bergamasque"   # HTML stripped

    # a non-work meta page still yields a card, just with no parsed composer
    assert cards[2].author is None


def test_disabled_raises_connector_unavailable(monkeypatch):
    monkeypatch.setattr(imslp, "settings", SimpleNamespace(imslp_enabled=False))
    with pytest.raises(ConnectorUnavailable):
        ImslpConnector(client=_FakeClient(SEARCH_PAYLOAD)).search("anything")
