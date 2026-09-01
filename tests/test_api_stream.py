"""Cache behaviour of the streaming search.

The regression these guard against: the stream used to decide "already ingested"
from the existence of the *piece* row. A piece whose ingest stored no cards (a
connector down or out of quota, or rows removed later) then became a permanent
negative cache — every repeat search replayed zero batches and the UI reported
"no results" forever, for a query that had worked before.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from scorekit import api
from scorekit.matching import MATCHER_VERSION
from scorekit.models import Card


class _FakeConnector:
    """Stands in for a real connector; records whether it was actually called."""

    def __init__(self, source: str, cards: list[Card]) -> None:
        self.source = source
        self._cards = cards
        self.calls = 0

    def __call__(self) -> "_FakeConnector":   # CONNECTORS holds classes, not instances
        return self

    def search(self, query: str, limit: int = 20) -> list[Card]:
        self.calls += 1
        return list(self._cards)

    def enrich_cards(self, cards: list[Card]) -> list[Card]:
        return cards


def _card(source: str, ext: str, title: str) -> Card:
    # The description names the piano because YouTube results pass through the piano
    # filter on the way in; these tests are about caching, so the fixture should not be
    # fighting that.
    return Card(
        source=source, external_id=ext, url=f"https://x/{ext}", title=title,
        metadata={"description_excerpt": "solo piano performance"},
    )


@pytest.fixture
def wiring(monkeypatch):
    """Patch out Supabase and the connector registry; return the mutable fake DB."""
    stored: dict[str, list[dict]] = {"youtube": [], "imslp": [], "musescore": []}
    pieces: list[dict] = []

    class _Q:
        def __init__(self, table): self.table, self.filters = table, {}
        def select(self, *a, **k): return self
        def limit(self, n): return self
        def eq(self, col, val):
            self.filters[col] = val
            return self
        def execute(self):
            if self.table == "pieces":
                return SimpleNamespace(data=list(pieces))
            src = self.filters.get("source")
            return SimpleNamespace(data=list(stored[src]) if src else [])

    monkeypatch.setattr(api, "get_client", lambda: SimpleNamespace(table=lambda t: _Q(t)))
    monkeypatch.setattr(api, "upsert_piece", lambda piece: "piece-1")
    monkeypatch.setattr(api, "retag_piece", lambda piece_id: 0)

    def _upsert_cards(piece_id, cards):
        for c in cards:
            stored[c.source].append({
                "id": c.external_id, "source": c.source, "title": c.title,
                "metadata": c.metadata,
            })
        return len(cards)

    monkeypatch.setattr(api, "upsert_cards", _upsert_cards)
    return SimpleNamespace(stored=stored, pieces=pieces, monkeypatch=monkeypatch)


def _cached(source: str, ext: str, title: str, mv: int | None = MATCHER_VERSION) -> dict:
    """A stored card row, scored by matcher version ``mv`` (None = pre-versioning)."""
    meta = {"match_score": 1.0} if mv is None else {"match_score": 1.0, "mv": mv}
    return {"id": ext, "source": source, "title": title, "metadata": meta}


def _connectors(wiring, **by_source: list[Card]) -> dict[str, _FakeConnector]:
    conns = {src: _FakeConnector(src, cards) for src, cards in by_source.items()}
    wiring.monkeypatch.setattr(api, "CONNECTORS", list(conns.values()))
    return conns


def test_cached_piece_with_no_cards_is_reingested(wiring):
    """The reported bug: a search that worked once then said 'no results' forever."""
    wiring.pieces.append({"id": "piece-1"})          # piece row exists…
    # …but every source table is empty, so the cache must be treated as a MISS
    conns = _connectors(wiring, youtube=[_card("youtube", "v1", "Nocturne Op. 48 No. 1")])

    batches = list(api._ingest_stream("Op 48 No 1", None, 25, refresh=False))

    assert conns["youtube"].calls == 1
    assert [c["title"] for b in batches for c in b] == ["Nocturne Op. 48 No. 1"]


def test_cached_piece_replays_without_calling_connectors(wiring):
    wiring.pieces.append({"id": "piece-1"})
    wiring.stored["youtube"].append(_cached("youtube", "v1", "Cached"))
    wiring.stored["imslp"].append(_cached("imslp", "p1", "Cached score"))
    wiring.stored["musescore"].append(_cached("musescore", "m1", "Cached listing"))
    conns = _connectors(wiring, youtube=[_card("youtube", "v2", "Fresh")])

    batches = list(api._ingest_stream("Op 48 No 1", None, 25, refresh=False))

    assert conns["youtube"].calls == 0          # fully cached: no API spend
    assert len(batches) == 3


def test_only_the_missing_source_is_ingested(wiring):
    """A source that was unavailable on the first search fills in on a later one,
    without re-spending quota on the sources that already have cards."""
    wiring.pieces.append({"id": "piece-1"})
    wiring.stored["youtube"].append(_cached("youtube", "v1", "Cached"))
    conns = _connectors(
        wiring,
        youtube=[_card("youtube", "v2", "Fresh")],
        musescore=[_card("musescore", "m1", "Nocturne Op.48 No.1")],
    )

    batches = list(api._ingest_stream("Op 48 No 1", None, 25, refresh=False))

    assert conns["youtube"].calls == 0          # cached, left alone
    assert conns["musescore"].calls == 1        # missing, ingested
    titles = [c["title"] for b in batches for c in b]
    assert titles == ["Cached", "Nocturne Op.48 No.1"]


def test_cards_scored_by_superseded_matching_are_reingested(wiring):
    """Regression: adding author matching fixed artist queries for new searches, while
    an already-cached "Birru" kept returning the single wrong card it matched by title.
    Dropped cards are never stored, so only a re-fetch can recover the right ones."""
    wiring.pieces.append({"id": "piece-1"})
    wiring.stored["youtube"].append(_cached("youtube", "old", "Interstellar - Birru", mv=None))
    conns = _connectors(wiring, youtube=[_card("youtube", "v1", "clair de lune but it's 3am")])
    conns["youtube"]._cards[0].author = "Birru"

    batches = list(api._ingest_stream("Birru", None, 25, refresh=False))

    assert conns["youtube"].calls == 1
    assert "clair de lune but it's 3am" in [c["title"] for b in batches for c in b]


def test_current_version_cards_are_still_replayed(wiring):
    wiring.pieces.append({"id": "piece-1"})
    wiring.stored["youtube"].append(_cached("youtube", "v1", "Cached", mv=MATCHER_VERSION))
    wiring.stored["imslp"].append(_cached("imslp", "p1", "Cached score"))
    wiring.stored["musescore"].append(_cached("musescore", "m1", "Cached listing"))
    conns = _connectors(wiring, youtube=[_card("youtube", "v2", "Fresh")])

    list(api._ingest_stream("Op 48 No 1", None, 25, refresh=False))
    assert conns["youtube"].calls == 0
