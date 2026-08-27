from types import SimpleNamespace

import pytest

from scorekit.connectors import imslp
from scorekit.connectors.base import ConnectorUnavailable
from scorekit.connectors.imslp import (
    ImslpConnector,
    _parse_title,
    _strip_html,
    _work_url,
    parse_workpage,
)
from scorekit.models import Card


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


# IMSLP's live search response has no `pageid`; fields are ns/size/snippet/
# timestamp/title/wordcount, and it includes #REDIRECT pages.
SEARCH_PAYLOAD = {
    "query": {
        "search": [
            {"title": "Clair de lune (Debussy, Claude)",
             "snippet": 'from <span class="searchmatch">Suite</span> bergamasque'},
            {"title": "6 Gymnopédies (Satie, Erik)", "snippet": ""},
            {"title": "IMSLP:Featured scores", "snippet": "meta page"},
            {"title": "Clair de lune (Indy, Vincent d')",
             "snippet": "#REDIRECT [[Clair de lune, Op.13 (Indy, Vincent d')]]"},  # dropped
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

    # redirect entry dropped; page title is the external_id (IMSLP omits pageid)
    assert len(cards) == 3
    assert [c.external_id for c in cards] == [
        "Clair de lune (Debussy, Claude)",
        "6 Gymnopédies (Satie, Erik)",
        "IMSLP:Featured scores",
    ]

    first = cards[0]
    assert first.source == "imslp"
    assert first.kind == "score"
    assert first.title == "Clair de lune"
    assert first.author == "Claude Debussy"
    assert first.url == "https://imslp.org/wiki/Clair_de_lune_(Debussy,_Claude)"
    assert first.metadata["imslp_page_title"] == "Clair de lune (Debussy, Claude)"
    assert first.metadata["snippet"] == "from Suite bergamasque"   # HTML stripped

    # a non-work meta page still yields a card, just with no parsed composer
    assert cards[2].author is None


def test_search_drops_redirects(monkeypatch):
    monkeypatch.setattr(imslp, "settings", SimpleNamespace(imslp_enabled=True))
    payload = {"query": {"search": [
        {"title": "X (Redirect, R)", "snippet": "#REDIRECT [[Real Page (Redirect, R)]]"},
    ]}}
    cards = ImslpConnector(client=_FakeClient(payload)).search("x")
    assert cards == []


def test_disabled_raises_connector_unavailable(monkeypatch):
    monkeypatch.setattr(imslp, "settings", SimpleNamespace(imslp_enabled=False))
    with pytest.raises(ConnectorUnavailable):
        ImslpConnector(client=_FakeClient(SEARCH_PAYLOAD)).search("anything")


# --- enrichment ---------------------------------------------------------------
WORKPAGE_WT = """{{#fte:imslppage
| *****SCORES***** =
{{#fte:imslpfile
|Copyright=Public Domain
}}
{{#fte:imslpfile
|Copyright=Creative Commons Attribution 4.0
}}
| *****GENERAL***** =
|Work Title=Suite bergamasque
|Opus/Catalogue Number=CD 82 ; L.75
|Year/Date of Composition=1890-1905
|Instrumentation=piano
|Piece Style=Romantic
}}"""

DISAMBIG_WT = (
    "This title can refer to three works.\n"
    "*{{LinkWorkN|Suite bergamasque|CD 82|Debussy|Claude|0}}\n"
    "[[Category:Debussy, Claude]]"
)


def test_parse_workpage_extracts_fields():
    md = parse_workpage(WORKPAGE_WT)
    assert md["is_work_page"] is True
    assert md["has_scores"] is True
    assert md["instrumentation"] == "piano"
    assert md["piece_style"] == "Romantic"
    assert md["year"] == "1890-1905"
    assert md["opus_catalogue"] == "CD 82 ; L.75"
    assert md["is_public_domain"] is True
    assert "Public Domain" in md["licenses"]
    assert "Creative Commons Attribution 4.0" in md["licenses"]


def test_parse_workpage_disambiguation():
    md = parse_workpage(DISAMBIG_WT)
    assert md["is_work_page"] is False
    assert md["is_disambiguation"] is True
    assert "instrumentation" not in md


def test_enrich_merges_metadata():
    parse_payload = {"parse": {"wikitext": {"*": WORKPAGE_WT}}}
    conn = ImslpConnector(client=_FakeClient(parse_payload))
    card = Card(source="imslp", external_id="Suite bergamasque, CD 82 (Debussy, Claude)",
                url="u", title="Suite bergamasque", kind="score",
                metadata={"imslp_page_title": "Suite bergamasque (Debussy, Claude)"})
    out = conn.enrich(card)
    assert out.metadata["instrumentation"] == "piano"
    assert out.metadata["is_public_domain"] is True
    assert out.metadata["enriched"] is True


def test_enrich_handles_failure_gracefully():
    class _BoomClient:
        def get(self, *a, **k):
            raise RuntimeError("network down")

    card = Card(source="imslp", external_id="x", url="u", title="X",
                metadata={"imslp_page_title": "X"})
    out = ImslpConnector(client=_BoomClient()).enrich(card)
    assert out.metadata["enriched"] is False


def test_enrich_skips_non_imslp_cards():
    card = Card(source="youtube", external_id="v", url="u", title="V", metadata={})
    # no client call should happen; a Boom client would raise if it did
    class _BoomClient:
        def get(self, *a, **k):
            raise AssertionError("should not fetch for non-imslp card")
    out = ImslpConnector(client=_BoomClient()).enrich(card)
    assert out is card
