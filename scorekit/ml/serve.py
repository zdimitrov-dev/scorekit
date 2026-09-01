"""Score cards with the promoted model, for the feed to rank by.

The learned model replaces one input to the existing ranker, not the ranker itself. It
supplies the relevance signal; the popularity blend, the diversity pass and the
already-engaged rules in ``recommend`` are unchanged. That keeps the feed's behaviour
identical apart from the part being tested, and means falling back to the heuristic
changes nothing else.

Returns ``None`` whenever the model cannot or should not be used, so every caller gets the
content ranker by default rather than a half-working one.
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

from .features import POSITION_FEATURE, build_profile, features_for
from .registry import load_model

log = logging.getLogger("scorekit.ml.serve")


def score_cards(
    cards: Sequence[dict[str, Any]],
    piece_tags: dict[str, list[tuple[str, str]]],
    weights: dict[tuple[str, str], float],
    positives: list[tuple[str, float]],
    force: bool = False,
) -> dict[str, float] | None:
    """``{card_id: relevance}`` from the promoted model, or None to use the heuristic.

    ``positives`` is the user's engaged ``(piece_id, weight)`` history, the same input the
    heuristic profile is built from, so both rankers see the same notion of taste.

    ``force`` uses a model that has not passed the gate, for side-by-side testing.
    """
    loaded = load_model()
    if loaded is None:
        return None
    # An unpromoted model is only ever used when explicitly asked for, so testing one
    # cannot change what anybody else sees.
    if not loaded.promoted and not force:
        return None
    # A model fitted with feed_position cannot be served: the position does not exist yet
    # at ranking time, since the scores are what decide it. Scoring would either raise on
    # the column count or silently feed NaN into a column the model was told to trust.
    # Refusing loudly beats a quiet fallback that looks like the model simply never helps.
    if POSITION_FEATURE in (loaded.feature_names or []):
        log.warning("saved model was trained with %s, which is unavailable at serving "
                    "time; using the content ranker", POSITION_FEATURE)
        return None
    if not positives:
        # A model trained on engagement has nothing to say about someone with none. Cold
        # start belongs to the content ranker, which at least has popularity to work with.
        return None

    try:
        import numpy as np

        profile = build_profile(positives, piece_tags, weights)
        rows = [features_for(c, piece_tags, profile, weights) for c in cards]
        if not rows:
            return None
        probs = loaded.model.predict_proba(np.asarray(rows, dtype=float))[:, 1]
        return {c["id"]: float(p) for c, p in zip(cards, probs)}
    except Exception:
        # Scoring must never break the feed; the heuristic is always a valid answer.
        log.exception("model scoring failed; falling back to the content ranker")
        return None
