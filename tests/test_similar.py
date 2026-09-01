"""'More like this' — cards similar to one specific card."""
from scorekit.recommend import idf_weights
from scorekit.similar import similar_cards

PIECE_TAGS = {
    "birru-laufey": [("creator", "birru"), ("format", "cover")],
    "birru":        [("creator", "birru"), ("format", "tutorial")],
    "laufey":       [("creator", "laufey"), ("format", "performance")],
    "chopin":       [("composer", "chopin"), ("era", "romantic"), ("form", "nocturne")],
    "bach":         [("composer", "bach"), ("era", "baroque"), ("form", "fugue")],
}
W = idf_weights(PIECE_TAGS)


def _card(cid, piece_id, title, author=None):
    return {"id": cid, "piece_id": piece_id, "title": title, "author": author,
            "source": "youtube", "metadata": {}}


ANCHOR = _card("a", "birru-laufey", "from the start - laufey", "Birru")
CORPUS = [
    ANCHOR,
    _card("b", "birru-laufey", "carousel - laufey", "Birru"),
    _card("c", "birru", "interstellar piano", "Birru"),
    _card("d", "laufey", "Laufey - From The Start (live)", "Laufey"),
    _card("e", "chopin", "Chopin Nocturne Op 9 No 2", "Rousseau"),
    _card("f", "bach", "Bach Fugue in G minor", "Kassia"),
]


def _order(anchor=ANCHOR, corpus=CORPUS, limit=10):
    return [c["id"] for c in similar_cards(anchor, corpus, PIECE_TAGS, W, limit)]


def test_the_anchor_is_never_returned():
    assert "a" not in _order()


def test_same_piece_ranks_first():
    # another recording of the very work being looked at is the most similar thing there is
    assert _order()[0] == "b"


def test_wholly_unrelated_pieces_are_dropped_not_merely_ranked_low():
    """Sharing nothing scores zero, and a zero-similarity card is left out rather than
    padding the strip — twelve slots of unrelated music is worse than four good ones."""
    order = _order()
    assert "c" in order          # same creator, kept
    assert "e" not in order      # a Chopin nocturne shares no tag and no word
    assert "f" not in order


def test_title_words_catch_what_tags_cannot():
    """A performer's repertoire is not part of a piece's tag set, so "Birru playing Laufey"
    and a Laufey recording share no tag at all. The words are the only link."""
    order = _order()
    assert "d" in order          # only the shared title words connect these two


def test_ranking_ignores_the_viewers_taste_entirely():
    # similar_cards takes no profile: opening a Birru card surfaces Birru whether or not
    # Birru appears anywhere in the viewer's history
    import inspect
    assert "profile" not in inspect.signature(similar_cards).parameters


def test_limit_is_respected():
    assert len(_order(limit=2)) == 2


def test_similarity_score_is_attached_for_debugging():
    out = similar_cards(ANCHOR, CORPUS, PIECE_TAGS, W, 3)
    assert all("similarity" in c["metadata"] for c in out)
    scores = [c["metadata"]["similarity"] for c in out]
    assert scores == sorted(scores, reverse=True)


def test_an_untagged_anchor_still_matches_on_title():
    orphan = _card("z", "unknown-piece", "from the start - laufey", "Someone")
    assert "b" in [c["id"] for c in similar_cards(orphan, CORPUS, PIECE_TAGS, W, 5)]
