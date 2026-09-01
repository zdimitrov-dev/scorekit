"""The learned ranker: features, labelling, and how the data is split."""
import math

from scorekit.ml.dataset import Dataset, build_dataset, is_negative, is_positive
from scorekit.ml.features import (
    FEATURE_NAMES, build_profile, corpus_weights, features_for,
)
from scorekit.ml.train import _split_indices

PIECE_TAGS = {
    "chopin-1": [("composer", "chopin"), ("era", "romantic"), ("form", "nocturne")],
    "chopin-2": [("composer", "chopin"), ("era", "romantic"), ("form", "ballade")],
    "bach-1": [("composer", "bach"), ("era", "baroque"), ("form", "fugue")],
}
W = corpus_weights(PIECE_TAGS)


def _card(piece_id, cid="c1", **meta):
    return {"id": cid, "piece_id": piece_id, "source": "youtube", "kind": None,
            "metadata": meta}


def _f(card, profile):
    return dict(zip(FEATURE_NAMES, features_for(card, PIECE_TAGS, profile, W)))


# --- features ---------------------------------------------------------------

def test_features_are_crossed_with_history_not_raw_tags():
    """One dense "does this match your history" column per tag kind, rather than one
    column per composer — with 43 composers and a few hundred rows, per-composer columns
    would each carry two or three examples."""
    liked_chopin = build_profile([("chopin-1", 1.0)], PIECE_TAGS, W)
    near = _f(_card("chopin-2"), liked_chopin)     # same composer and era
    far = _f(_card("bach-1"), liked_chopin)        # shares nothing
    assert near["affinity_composer"] > far["affinity_composer"]
    assert near["affinity_era"] > far["affinity_era"]
    assert near["affinity_overall"] > far["affinity_overall"]


def test_each_kind_gets_its_own_axis_so_weighting_can_be_learned():
    # this is the whole point: KEY_WEIGHTS says composer 1.0 / instrumentation 0.25 by
    # hand, and the model has to be able to disagree
    assert "affinity_composer" in FEATURE_NAMES
    assert "affinity_instrumentation" in FEATURE_NAMES


def test_missing_view_count_is_nan_not_zero():
    """A score page has no view count because IMSLP has no such concept, which is not the
    same fact as a video nobody watched. Trees can branch on missing; zero lies."""
    empty = build_profile([], PIECE_TAGS, W)
    assert math.isnan(_f(_card("chopin-1"), empty)["log_views"])
    assert _f(_card("chopin-1", view_count=1000), empty)["log_views"] > 0


def test_profile_is_normalised_so_heavy_users_are_comparable():
    light = build_profile([("chopin-1", 1.0)], PIECE_TAGS, W)
    heavy = build_profile([("chopin-1", 1.0)] * 30, PIECE_TAGS, W)
    for p in (light, heavy):
        assert math.isclose(math.sqrt(sum(v * v for v in p.vector.values())), 1.0, abs_tol=1e-9)


# --- labelling --------------------------------------------------------------

def test_long_clicks_are_positives_and_short_ones_are_not():
    """Likes are rare — most people never press the button — so dwell is the strongest
    behavioural positive the feed produces."""
    assert is_positive({"action": "click", "dwell_ms": 20000})
    assert not is_positive({"action": "click", "dwell_ms": 1500})
    assert is_negative({"action": "click", "dwell_ms": 1500})
    assert is_positive({"action": "like"})
    assert is_positive({"action": "save"})
    assert is_negative({"action": "impression", "dwell_ms": 3000})


def test_profile_never_contains_the_row_it_is_predicting():
    """Leakage check. Building the profile from all of a user's history and then predicting
    a held-out like means the profile already contains that like's tags — the model scores
    near-perfectly having learned nothing."""
    events = [
        {"id": i, "user_id": "u", "action": "like", "card_id": "c1",
         "piece_id": "chopin-1", "created_at": f"2026-01-0{i}"}
        for i in range(1, 6)
    ]
    cards = {"c1": _card("chopin-1")}
    data = build_dataset(events, cards, PIECE_TAGS, W, warmup=0.0)
    # the very first row is scored against an empty profile, so its affinity must be 0
    assert data.X[0][FEATURE_NAMES.index("affinity_overall")] == 0.0
    # and later rows, built from earlier likes, must not be
    assert data.X[-1][FEATURE_NAMES.index("affinity_overall")] > 0.0


def test_warmup_rows_seed_the_profile_without_being_trained_on():
    events = [
        {"id": i, "user_id": "u", "action": "like" if i < 3 else "impression",
         "card_id": "c1", "piece_id": "chopin-1", "created_at": f"2026-01-0{i}"}
        for i in range(1, 11)
    ]
    data = build_dataset(events, {"c1": _card("chopin-1")}, PIECE_TAGS, W, warmup=0.4)
    assert len(data) == 6      # 10 events, first 4 held back as warm-up


def test_unknown_cards_are_skipped_rather_than_crashing():
    events = [{"id": 1, "user_id": "u", "action": "like", "card_id": "gone",
               "piece_id": "chopin-1", "created_at": "2026-01-01"}]
    assert len(build_dataset(events, {}, PIECE_TAGS, W, warmup=0.0)) == 0


# --- splitting --------------------------------------------------------------

def _grouped(groups):
    d = Dataset()
    d.groups = groups
    d.X = [[0.0]] * len(groups)
    d.y = [0] * len(groups)
    d.weight = [1.0] * len(groups)
    return d


def test_chronological_split_holds_out_each_users_own_future():
    """Regression: splitting the pooled rows put every test row inside a single user,
    because rows are grouped by user — so it silently measured cross-user generalisation
    while claiming to measure the production question."""
    data = _grouped(["a"] * 10 + ["b"] * 10)
    train, test = _split_indices(data, 0.3, "chronological")
    assert {data.groups[i] for i in train} == {"a", "b"}
    assert {data.groups[i] for i in test} == {"a", "b"}


def test_cross_user_split_holds_out_whole_users():
    data = _grouped(["a"] * 10 + ["b"] * 10 + ["c"] * 10)
    train, test = _split_indices(data, 0.34, "cross_user")
    train_users = {data.groups[i] for i in train}
    test_users = {data.groups[i] for i in test}
    assert not (train_users & test_users)      # no user appears on both sides


# --- the promotion gate -----------------------------------------------------

def test_gate_refuses_a_model_that_cannot_beat_the_heuristic():
    from scorekit.ml.registry import gate
    ok, reason = gate(auc=0.60, heuristic_auc=0.59, positives=200)
    assert not ok and "does not beat the heuristic" in reason


def test_gate_refuses_a_model_no_better_than_chance():
    from scorekit.ml.registry import gate
    ok, reason = gate(auc=0.41, heuristic_auc=0.40, positives=200)
    assert not ok and "chance" in reason


def test_gate_refuses_until_there_are_enough_positives():
    """A handful of likes in the held-out split makes AUC swing on one row landing
    differently, so a high score there is not evidence of anything."""
    from scorekit.ml.registry import gate, MIN_POSITIVES
    ok, reason = gate(auc=0.99, heuristic_auc=0.50, positives=MIN_POSITIVES - 1)
    assert not ok and "positive examples" in reason


def test_gate_accepts_a_clear_win_on_enough_data():
    from scorekit.ml.registry import gate
    ok, _ = gate(auc=0.78, heuristic_auc=0.70, positives=200)
    assert ok


def test_serving_falls_back_when_no_model_is_promoted():
    from scorekit.ml.serve import score_cards
    assert score_cards([_card("chopin-1")], PIECE_TAGS, W, [("chopin-1", 1.0)]) is None


def test_ranker_uses_a_learned_relevance_when_given_one():
    """The model replaces one input, not the ranker: popularity, diversity and the
    already-engaged rules stay identical, so falling back changes nothing else."""
    from scorekit.recommend import rank_cards
    cards = [
        {"id": "a", "piece_id": "chopin-1", "title": "a", "metadata": {"view_count": 10}},
        {"id": "b", "piece_id": "bach-1", "title": "b", "metadata": {"view_count": 9_000_000}},
    ]
    ranked = rank_cards(cards, PIECE_TAGS, signals=[], relevance={"a": 0.99, "b": 0.01})
    assert [c["id"] for c in ranked][0] == "a"
