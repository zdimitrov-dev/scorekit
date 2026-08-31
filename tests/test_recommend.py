import math

from scorekit.recommend import (
    POPULARITY_WEIGHT,
    affinity,
    build_profile,
    idf_weights,
    rank_cards,
)

# A small corpus: two Chopin nocturnes, a Debussy piece, and a Bach fugue.
PIECE_TAGS = {
    "chopin-1": [("composer", "chopin"), ("era", "romantic"), ("form", "nocturne"),
                 ("public_domain", "true")],
    "chopin-2": [("composer", "chopin"), ("era", "romantic"), ("form", "nocturne"),
                 ("public_domain", "true")],
    "debussy":  [("composer", "debussy"), ("era", "impressionist"), ("form", "suite"),
                 ("public_domain", "true")],
    "bach":     [("composer", "bach"), ("era", "baroque"), ("form", "fugue"),
                 ("public_domain", "true")],
}


def _card(piece_id, cid=None, views=0):
    return {
        "id": cid or f"{piece_id}-card",
        "piece_id": piece_id,
        "title": piece_id,
        "metadata": {"view_count": views},
    }


CARDS = [_card(p, views=1000) for p in PIECE_TAGS]


def test_idf_downweights_ubiquitous_tags():
    w = idf_weights(PIECE_TAGS)
    # every piece is public domain; only one is by Debussy
    assert w[("public_domain", "true")] < w[("composer", "debussy")]
    assert w[("composer", "chopin")] < w[("composer", "bach")]  # chopin appears twice


def test_taste_bearing_tag_kinds_outweigh_incidental_ones():
    # equally rare tags are not equally meaningful: sharing a composer says far more
    # than sharing an instrument, and in piano repertoire almost everything is piano
    tags = {
        "a": [("composer", "chopin"), ("instrumentation", "piano")],
        "b": [("composer", "bach"), ("instrumentation", "organ")],
    }
    w = idf_weights(tags)
    assert w[("composer", "chopin")] > w[("instrumentation", "piano")]


def test_a_hairball_does_not_outrank_a_genuinely_similar_piece():
    """Regression: a heterogeneous "piece" that had accumulated many incidental tags
    matched every profile and outranked the real neighbour — liking Debussy surfaced it
    above Satie, who shares the era."""
    piece_tags = {
        "debussy": [("composer", "debussy"), ("era", "impressionist"),
                    ("instrumentation", "piano"), ("style", "romantic")],
        "satie": [("composer", "satie"), ("era", "impressionist")],
        "hairball": [("composer", "misc"), ("era", "romantic"), ("form", "waltz"),
                     ("form", "prelude"), ("style", "romantic"), ("style", "classical"),
                     ("instrumentation", "piano"), ("instrumentation", "violin"),
                     ("instrumentation", "cello"), ("instrumentation", "voice"),
                     ("public_domain", "true")],
    }
    cards = [_card(p, views=1000) for p in piece_tags]
    ranked = rank_cards(cards, piece_tags, signals=[("debussy", "like")],
                        exclude_piece_ids=["debussy"])
    assert [c["piece_id"] for c in ranked][0] == "satie"


def test_profile_is_normalised_regardless_of_signal_count():
    light = build_profile([("chopin-1", "like")], PIECE_TAGS)
    heavy = build_profile([("chopin-1", "like")] * 20, PIECE_TAGS)
    for vec in (light, heavy):
        assert math.isclose(math.sqrt(sum(v * v for v in vec.values())), 1.0, abs_tol=1e-9)


def test_save_outweighs_like():
    liked = build_profile([("chopin-1", "like"), ("debussy", "save")], PIECE_TAGS)
    # the saved piece's distinctive tag should dominate the liked one's
    assert liked[("composer", "debussy")] > liked[("composer", "chopin")]


def test_skip_is_the_negative_signal():
    profile = build_profile([("chopin-1", "like"), ("bach", "skip")], PIECE_TAGS)
    assert profile[("composer", "chopin")] > 0
    assert profile[("composer", "bach")] < 0


def test_affinity_prefers_the_similar_piece():
    weights = idf_weights(PIECE_TAGS)
    profile = build_profile([("chopin-1", "like")], PIECE_TAGS, weights)
    # chopin-2 shares composer/era/form with the liked piece; bach shares nothing but PD
    assert affinity(PIECE_TAGS["chopin-2"], profile, weights) > affinity(
        PIECE_TAGS["bach"], profile, weights
    )


def test_liking_chopin_lifts_the_other_chopin_above_unrelated_pieces():
    ranked = rank_cards(CARDS, PIECE_TAGS, signals=[("chopin-1", "like")], limit=4)
    order = [c["piece_id"] for c in ranked]
    assert order.index("chopin-2") < order.index("debussy")
    assert order.index("chopin-2") < order.index("bach")


def test_the_liked_piece_itself_can_be_held_out_of_the_feed():
    ranked = rank_cards(
        CARDS, PIECE_TAGS, signals=[("chopin-1", "like")], exclude_piece_ids=["chopin-1"]
    )
    assert [c["piece_id"] for c in ranked][0] == "chopin-2"


def test_already_engaged_pieces_can_be_excluded():
    ranked = rank_cards(
        CARDS, PIECE_TAGS, signals=[("chopin-1", "like")],
        exclude_piece_ids=["chopin-1", "chopin-2"],
    )
    assert {c["piece_id"] for c in ranked} == {"debussy", "bach"}


def test_cold_start_falls_back_to_popularity():
    cards = [_card("bach", views=10), _card("debussy", views=5_000_000)]
    ranked = rank_cards(cards, PIECE_TAGS, signals=[], limit=2)
    assert ranked[0]["piece_id"] == "debussy"
    assert ranked[0]["metadata"]["rec"]["affinity"] == 0.0


def test_diversify_breaks_up_a_run_of_one_piece():
    # eight cards for the liked piece's twin, one for something else
    cards = [_card("chopin-2", cid=f"c{i}", views=1000) for i in range(8)]
    cards.append(_card("bach", cid="bach-1", views=1000))
    ranked = rank_cards(cards, PIECE_TAGS, signals=[("chopin-1", "like")], limit=3)
    assert [c["piece_id"] for c in ranked[:2]] == ["chopin-2", "bach"]


def test_scores_are_explainable():
    ranked = rank_cards(CARDS, PIECE_TAGS, signals=[("chopin-1", "like")], limit=1)
    rec = ranked[0]["metadata"]["rec"]
    assert set(rec) == {"affinity", "popularity", "score"}


def test_popularity_weight_is_a_minority_of_the_score():
    # taste must dominate; popularity only breaks ties and covers a thin profile
    assert 0 < POPULARITY_WEIGHT < 0.5


def test_untagged_pieces_still_rank_without_crashing():
    cards = [_card("unknown-piece", views=100), _card("chopin-2", views=100)]
    ranked = rank_cards(cards, PIECE_TAGS, signals=[("chopin-1", "like")], limit=2)
    assert len(ranked) == 2
    assert ranked[0]["piece_id"] == "chopin-2"
