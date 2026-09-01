"""Catalogue seeding — walking IMSLP instead of waiting to be searched."""
from types import SimpleNamespace

from scorekit.connectors.imslp import PIANO_CATEGORIES, ImslpConnector
from scorekit.jobs.seed import _priority


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    """Serves canned responses in order and records the params it was called with."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = []

    def get(self, url, params=None):
        self.calls.append(params or {})
        return _Resp(self._payloads.pop(0))


def _members(*titles):
    return {"query": {"categorymembers": [{"title": t} for t in titles]}}


def test_category_members_follows_legacy_continuation():
    """IMSLP runs an older MediaWiki that returns its token under `query-continue`, not
    `continue` — reading only the modern key would silently stop at the first page."""
    page1 = {**_members("A (X, Y)", "B (X, Y)"),
             "query-continue": {"categorymembers": {"cmcontinue": "TOKEN"}}}
    page2 = _members("C (X, Y)")
    client = _FakeClient([page1, page2])

    titles = ImslpConnector(client=client).category_members("Category:X, Y")

    assert titles == ["A (X, Y)", "B (X, Y)", "C (X, Y)"]
    assert client.calls[1]["cmcontinue"] == "TOKEN"


def test_category_members_stops_at_limit_without_extra_requests():
    page1 = {**_members("A (X, Y)", "B (X, Y)"),
             "query-continue": {"categorymembers": {"cmcontinue": "TOKEN"}}}
    client = _FakeClient([page1])
    assert ImslpConnector(client=client).category_members("Category:X, Y", limit=2) == [
        "A (X, Y)", "B (X, Y)",
    ]
    assert len(client.calls) == 1


def test_piano_titles_keeps_only_pages_in_a_piano_category():
    # a composer's category holds everything they wrote; seeding it unfiltered would put
    # string quartets on a piano platform
    payload = {"query": {"pages": {
        "1": {"title": "Ballade No.1 (Chopin, Frédéric)",
              "categories": [{"title": "Category:For piano"}]},
        "2": {"title": "Cello Sonata (Chopin, Frédéric)"},          # no piano category
        "3": {"title": "Goldberg Variations (Bach, Johann Sebastian)",
              "categories": [{"title": "Category:For keyboard"}]},
    }}}
    client = _FakeClient([payload])
    kept = ImslpConnector(client=client).piano_titles(["a", "b", "c"])

    assert sorted(kept) == ["Ballade No.1 (Chopin, Frédéric)",
                            "Goldberg Variations (Bach, Johann Sebastian)"]
    assert client.calls[0]["clcategories"] == "|".join(PIANO_CATEGORIES)


def test_piano_titles_batches_at_the_api_title_limit():
    # MediaWiki accepts at most 50 titles per request
    client = _FakeClient([{"query": {"pages": {}}} for _ in range(3)])
    ImslpConnector(client=client).piano_titles([f"t{i}" for i in range(120)])
    assert len(client.calls) == 3
    assert [len(c["titles"].split("|")) for c in client.calls] == [50, 50, 20]


def test_keyboard_and_harpsichord_count_as_piano():
    """Requiring "For piano" alone collapses the baroque: IMSLP files that music by the
    instrument it was written for, leaving Bach with 1 work and Scarlatti with 0."""
    assert "Category:For keyboard" in PIANO_CATEGORIES
    assert "Category:For harpsichord" in PIANO_CATEGORIES
    # arrangements are excluded: they carry piano reductions of symphonies and concertos
    assert "Category:For piano (arr)" not in PIANO_CATEGORIES


def test_card_for_page_parses_the_composer_out_of_the_title():
    card = ImslpConnector(client=_FakeClient([])).card_for_page(
        "Ballade No.1, Op.23 (Chopin, Frédéric)"
    )
    assert card is not None
    assert card.title == "Ballade No.1, Op.23"
    assert card.author == "Frédéric Chopin"
    assert card.external_id == "Ballade No.1, Op.23 (Chopin, Frédéric)"
    assert card.kind == "score"


def test_priority_puts_recognisable_repertoire_first():
    """A composer's category is alphabetical, which for Chopin opens with "2 Mazurkas,
    B.16" rather than the Ballades — so a small per-composer cap would seed the obscure
    end of every composer."""
    titles = [
        "2 Mazurkas, B.16 (Chopin, Frédéric)",
        "Ballade No.1, Op.23 (Chopin, Frédéric)",
        "Allegretto in F-sharp major (Chopin, Frédéric)",
    ]
    assert sorted(titles, key=_priority)[0] == "Ballade No.1, Op.23 (Chopin, Frédéric)"
    # something with neither a form nor an opus sorts last
    assert sorted(titles, key=_priority)[-1] == "Allegretto in F-sharp major (Chopin, Frédéric)"
