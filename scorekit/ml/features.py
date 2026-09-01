"""Turning a (user, card) pair into a feature vector.

The central design choice is what a "user" contributes to the row. Feeding raw tags needs
one column per composer, and with 43 composers and a few hundred rows each column would
carry two or three examples.

Instead the features are crossed with the user's history: not "is this Chopin?" but "how
much does this user's history overlap this piece on the composer axis?". That turns 43
sparse columns into one dense one that means the same thing for every user and works from
the first like.

Because there is a separate affinity per tag kind, the model can learn how much each kind
matters. ``recommend.KEY_WEIGHTS`` says composer matters 1.0 and instrumentation 0.25
because those numbers were chosen by hand; the model derives them from behaviour, so the
two can be compared. The heuristic ranker is therefore a feature generator for the learned
one, not its rival.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable

from ..recommend import affinity as tag_affinity
from ..recommend import idf_weights

# Tag kinds given their own affinity column. Anything else still counts toward the overall
# affinity, but does not get a dedicated axis.
AFFINITY_KEYS = ("composer", "era", "form", "format", "instrumentation", "creator")

FEATURE_NAMES: list[str] = [
    # --- how well this piece matches what the user has engaged with -------------
    "affinity_overall",
    *[f"affinity_{k}" for k in AFFINITY_KEYS],
    "seen_composer_before",     # times this composer appeared in the user's positives
    "seen_era_before",
    # --- the card itself ---------------------------------------------------------
    "match_score",              # attribution: how well the card matches its own piece
    "log_views",                # NaN when the source has no view metric (see below)
    "duration_min",
    "n_tags",                   # how well described the piece is
    "is_youtube",
    "is_imslp",
    "is_musescore",
    "is_tutorial",
    "is_cover",
    "is_performance",
    "is_compilation",
    "has_sheet_link",
    "is_public_domain",
]

# Where the card sat in the feed when it was logged.
#
# Kept apart from FEATURE_NAMES because it is not an ordinary feature. At training time it
# is known; at serving time it does not exist yet, since the scores are what decide the
# positions. A model that leans on it therefore looks better offline and gains nothing in
# production, which is worth measuring rather than assuming. Off by default; enable with
# ``feature_names(with_position=True)`` and the matching argument to ``features_for``.
POSITION_FEATURE = "feed_position"


def feature_names(with_position: bool = False) -> list[str]:
    return [*FEATURE_NAMES, POSITION_FEATURE] if with_position else list(FEATURE_NAMES)


class UserProfile:
    """What the model knows about a user: their engaged tags, weighted by signal strength."""

    def __init__(self, tag_counts: Counter[tuple[str, str]] | None = None,
                 vector: dict[tuple[str, str], float] | None = None) -> None:
        self.tag_counts = tag_counts or Counter()
        self.vector = vector or {}

    @property
    def is_empty(self) -> bool:
        return not self.vector


def build_profile(
    positives: Iterable[tuple[str, float]],
    piece_tags: dict[str, list[tuple[str, str]]],
    weights: dict[tuple[str, str], float],
) -> UserProfile:
    """Build a profile from ``(piece_id, weight)`` positive engagements.

    Deliberately mirrors ``recommend.build_profile`` so the learned model and the heuristic
    see the *same* notion of taste — otherwise a head-to-head comparison would be measuring
    two different profiles rather than two different rankers.
    """
    counts: Counter[tuple[str, str]] = Counter()
    vector: dict[tuple[str, str], float] = {}
    for piece_id, weight in positives:
        for tag in piece_tags.get(piece_id, ()):
            counts[tag] += 1
            vector[tag] = vector.get(tag, 0.0) + weight * weights.get(tag, 1.0)

    norm = math.sqrt(sum(v * v for v in vector.values()))
    if norm:
        vector = {t: v / norm for t, v in vector.items()}
    return UserProfile(counts, vector)


def _subset_affinity(tags, profile, weights, key: str) -> float:
    """Affinity restricted to one tag kind — the column that lets the model decide how much
    that kind is worth, instead of being told."""
    subset = [t for t in tags if t[0] == key]
    if not subset:
        return 0.0
    return tag_affinity(subset, profile.vector, weights)


def features_for(
    card: dict[str, Any],
    piece_tags: dict[str, list[tuple[str, str]]],
    profile: UserProfile,
    weights: dict[tuple[str, str], float],
    position: float | None = None,
    with_position: bool = False,
) -> list[float]:
    """One feature row. Order matches ``feature_names(with_position)``.

    ``position`` is where the card sat in the feed, known only at training time. When
    ``with_position`` is on and none is supplied the column is NaN, which is exactly what
    serving would see.
    """
    piece_id = card.get("piece_id") or (card.get("piece") or {}).get("id")
    tags = piece_tags.get(piece_id, [])
    meta = card.get("metadata") or {}

    views = meta.get("view_count")
    # NaN, not 0. A score page has no view count because IMSLP has no such concept, which
    # is not the same fact as a video nobody watched — and the trees read missingness as
    # its own branch rather than as an unpopular video. This is exactly the conflation the
    # heuristic ranker still has (see PROJECT_CONTEXT, known cleanup).
    log_views = math.log10(1 + views) if isinstance(views, (int, float)) and views > 0 \
        else float("nan")

    duration = meta.get("duration_seconds")
    kind = card.get("kind")
    source = card.get("source")

    return [
        tag_affinity(tags, profile.vector, weights),
        *[_subset_affinity(tags, profile, weights, k) for k in AFFINITY_KEYS],
        float(sum(n for (k, _v), n in profile.tag_counts.items() if k == "composer"
                  and (k, _v) in set(tags))),
        float(sum(n for (k, _v), n in profile.tag_counts.items() if k == "era"
                  and (k, _v) in set(tags))),
        float(meta.get("match_score") or 0.0),
        log_views,
        (duration / 60.0) if isinstance(duration, (int, float)) else float("nan"),
        float(len(tags)),
        float(source == "youtube"),
        float(source == "imslp"),
        float(source == "musescore"),
        float(kind == "tutorial"),
        float(kind == "cover"),
        float(kind == "performance"),
        float(bool(meta.get("is_compilation"))),
        float(bool(meta.get("has_sheet_music_link"))),
        float(any(k == "public_domain" for k, _ in tags)),
    ] + ([float(position) if position is not None else float("nan")]
         if with_position else [])


def corpus_weights(piece_tags: dict[str, list[tuple[str, str]]]) -> dict[tuple[str, str], float]:
    """IDF × key weights over the corpus — shared with the heuristic ranker."""
    return idf_weights(piece_tags)
