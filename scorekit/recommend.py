"""Content-based recommender — rank cards against a user's tag profile.

This is the **non-collaborative** half of the home feed: it recommends from what a piece
*is* (its ``piece_tags``), never from what other users did. That ordering is deliberate —
collaborative filtering cannot say anything about a user with no neighbours or a piece
nobody has touched yet, and this project starts with exactly one user and a corpus that
grows one search at a time. Content-based ranking works from the first like, so it is
both the launch ranker and, later, the cold-start fallback the collaborative model defers
to. The two are designed to compose: ``score = w·content + (1-w)·collaborative``.

The pipeline is four steps:

1. **Profile** — turn liked/saved pieces into a weighted tag vector (``build_profile``).
2. **Score** — cosine-style match of each candidate piece's tags against that vector,
   with rarer tags counting for more (``idf_weights``).
3. **Blend** — mix in a small popularity prior so a thin profile still ranks sensibly.
4. **Diversify** — greedily re-order so one piece or composer cannot own the board.

Nothing here talks to the database; ``scorekit/api.py`` supplies rows and stores nothing
back. That keeps the ranker unit-testable and lets the profile source change (localStorage
today, the ``interactions`` table once Phase 5 lands) without touching the algorithm.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any, Iterable, Sequence

# How strongly a signal counts toward the profile. Saving is a deliberate "keep this"
# and outranks a like; an explicit skip is the negative (there is no dislike button).
SIGNAL_WEIGHTS: dict[str, float] = {
    "save": 1.5,
    "like": 1.0,
    "click": 0.4,
    "skip": -0.8,
}

# Share of the final score that comes from popularity rather than tag match. Small but
# non-zero: it breaks ties sensibly and keeps a brand-new profile from ranking randomly.
#
# This weight only means what it says because both terms are rescaled across the candidate
# pool first (see `_rescale`). Raw cosine and the popularity measure live on completely
# different scales: two pieces sharing one of three tags score ~0.15 by cosine no matter
# how related they are, while any popular video sits at 0.75-0.85 popularity. Blending
# those directly let popularity outweigh the *best possible* tag match, so a "personalized"
# feed was a popularity feed with a nudge.
POPULARITY_WEIGHT = 0.15

# Repeats of an already-shown piece (or composer/creator) fade **multiplicatively** as the
# list is built, so a strongly-matching piece leads with several cards and then yields.
#
# Subtracting a flat penalty instead was wrong in both directions. Scores live in [0, 1]
# after rescaling, so a penalty large enough to prevent a wall of one piece (1.0) drove the
# second card straight to zero — liking several Birru uploads surfaced exactly one of them
# and buried the rest under unrelated cards, which reads as the likes being ignored. A
# penalty small enough to avoid that let one piece own the whole board. A decay has no such
# cliff: it keeps liked material clustered near the top without letting it run forever.
PIECE_DECAY = 0.72
GROUP_DECAY = 0.85

# Hard ceiling on how many cards of one piece may sit consecutively. The decay alone is a
# *relative* rule, so when everything else scores near zero — a thin corpus, or a cold
# profile where nothing else matches at all — a single piece can still take every slot.
# This makes the guarantee absolute and independent of how the scores happen to fall.
MAX_CONSECUTIVE_PER_PIECE = 3


# How much each kind of tag expresses *taste*, independent of how rare it happens to be.
# IDF alone measures rarity, which is not the same thing and is unstable on a small
# corpus: two pieces sharing a composer are alike in a way two pieces that merely both
# involve a piano are not — and in piano repertoire nearly everything involves a piano.
# Without this, a heterogeneous "piece" that accumulated many incidental tags matched
# every profile through low-information overlap and outranked genuinely similar works.
KEY_WEIGHTS: dict[str, float] = {
    "composer": 1.0,
    "creator": 1.0,   # for artist entries, the channel is the whole point
    "era": 0.9,
    "form": 0.7,
    "style": 0.4,
    "instrumentation": 0.25,
    "public_domain": 0.1,
}
DEFAULT_KEY_WEIGHT = 0.5


def idf_weights(piece_tags: dict[str, list[tuple[str, str]]]) -> dict[tuple[str, str], float]:
    """Per-tag weight: how *rare* it is (IDF) scaled by how much its kind matters.

    Without the IDF half, ``public_domain=true`` — which nearly every piece carries —
    would count as much as ``composer=chopin``. Without the ``KEY_WEIGHTS`` half, a tag
    that is rare only because the corpus is small counts as though it were meaningful.
    """
    n = len(piece_tags) or 1
    counts: Counter[tuple[str, str]] = Counter()
    for tags in piece_tags.values():
        counts.update(set(tags))
    return {
        tag: math.log(1 + n / (1 + c)) * KEY_WEIGHTS.get(tag[0], DEFAULT_KEY_WEIGHT)
        for tag, c in counts.items()
    }


def build_profile(
    signals: Iterable[tuple[str, str]],
    piece_tags: dict[str, list[tuple[str, str]]],
    weights: dict[tuple[str, str], float] | None = None,
) -> dict[tuple[str, str], float]:
    """Build a weighted tag vector from ``(piece_id, action)`` signals.

    Each engaged piece contributes its tags, scaled by the action's weight and by tag
    rarity. The result is L2-normalised so a user with 50 likes is compared on the same
    scale as one with three — otherwise heavy users would score every candidate higher
    and the popularity blend below would stop meaning anything.
    """
    weights = weights if weights is not None else idf_weights(piece_tags)
    profile: dict[tuple[str, str], float] = defaultdict(float)
    for piece_id, action in signals:
        w = SIGNAL_WEIGHTS.get(action, 0.0)
        if not w:
            continue
        for tag in piece_tags.get(piece_id, ()):
            profile[tag] += w * weights.get(tag, 1.0)

    norm = math.sqrt(sum(v * v for v in profile.values()))
    if norm:
        for tag in profile:
            profile[tag] /= norm
    return dict(profile)


def affinity(
    tags: Sequence[tuple[str, str]],
    profile: dict[tuple[str, str], float],
    weights: dict[tuple[str, str], float],
) -> float:
    """Match between one piece's tags and the profile, in roughly [-1, 1].

    Normalised by the piece's own tag magnitude so a heavily-tagged piece does not
    outscore a sparse one purely for having more tags to match on.
    """
    if not tags or not profile:
        return 0.0
    dot = sum(profile.get(t, 0.0) * weights.get(t, 1.0) for t in set(tags))
    norm = math.sqrt(sum(weights.get(t, 1.0) ** 2 for t in set(tags)))
    return dot / norm if norm else 0.0


def _popularity(card: dict[str, Any]) -> float:
    """View count squashed to [0, 1]. Log-scaled — the gap between 1k and 10k views
    matters, the gap between 5M and 6M does not."""
    views = (card.get("metadata") or {}).get("view_count") or 0
    return min(1.0, math.log10(1 + views) / 8.0) if views > 0 else 0.0


def _rescale(values: Sequence[float]) -> list[float]:
    """Min-max the values into [0, 1] so they can be blended meaningfully.

    An all-equal input (notably every affinity being 0.0, the cold-start case) collapses
    to all-zero rather than dividing by zero — which correctly makes that signal carry no
    information and hands the ordering to the other term.
    """
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def rank_cards(
    cards: Sequence[dict[str, Any]],
    piece_tags: dict[str, list[tuple[str, str]]],
    signals: Iterable[tuple[str, str]] = (),
    limit: int = 60,
    exclude_piece_ids: Iterable[str] = (),
    exclude_card_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Rank ``cards`` for a user, most relevant first.

    Each returned card carries a ``metadata['rec']`` breakdown — the raw affinity, the
    popularity prior and the final score — so the feed can be explained and debugged
    rather than being an opaque ordering. With no signals this degrades to a diversified
    popularity feed, which is the correct cold-start behaviour.
    """
    weights = idf_weights(piece_tags)
    profile = build_profile(signals, piece_tags, weights)
    excluded_pieces = set(exclude_piece_ids)
    excluded_cards = set(exclude_card_ids)

    candidates: list[tuple[dict[str, Any], float, float]] = []
    for card in cards:
        piece_id = card.get("piece_id") or (card.get("piece") or {}).get("id")
        if piece_id in excluded_pieces or card.get("id") in excluded_cards:
            continue
        candidates.append((
            card,
            affinity(piece_tags.get(piece_id, ()), profile, weights),
            _popularity(card),
        ))

    # Rescale within the pool before blending, so POPULARITY_WEIGHT is a real proportion.
    affs = _rescale([a for _c, a, _p in candidates])
    pops = _rescale([p for _c, _a, p in candidates])

    scored = [
        ((1 - POPULARITY_WEIGHT) * affs[i] + POPULARITY_WEIGHT * pops[i], a, p, card)
        for i, (card, a, p) in enumerate(candidates)
    ]
    scored.sort(key=lambda row: -row[0])
    return _diversify(scored, piece_tags, limit)


def _group_of(piece_id: str, piece_tags: dict[str, list[tuple[str, str]]]) -> str | None:
    """What a piece belongs to for diversity purposes: its composer, or for an artist
    entry (which has no composer) the creator whose channel it is."""
    tags = piece_tags.get(piece_id, ())
    return next(
        (v for k, v in tags if k == "composer"),
        next((v for k, v in tags if k == "creator"), None),
    )


def _diversify(
    scored: list[tuple[float, float, float, dict[str, Any]]],
    piece_tags: dict[str, list[tuple[str, str]]],
    limit: int,
) -> list[dict[str, Any]]:
    """Greedily pick the best remaining card, fading pieces and composers already picked.
    A simple MMR: it costs a little relevance per slot and buys a board that looks like a
    feed instead of a search result."""
    remaining = list(scored)
    seen_pieces: Counter[str] = Counter()
    seen_groups: Counter[str] = Counter()
    out: list[dict[str, Any]] = []

    run_piece: str | None = None   # piece occupying the current consecutive run
    run_length = 0

    while remaining and len(out) < limit:
        blocked = run_piece if run_length >= MAX_CONSECUTIVE_PER_PIECE else None
        best_i, best_val, best_row = -1, -math.inf, None
        for i, row in enumerate(remaining):
            base, _aff, _pop, card = row
            piece_id = card.get("piece_id") or (card.get("piece") or {}).get("id")
            if piece_id == blocked:
                continue
            value = base * (PIECE_DECAY ** seen_pieces[piece_id])
            group = _group_of(piece_id, piece_tags)
            if group:
                value *= GROUP_DECAY ** seen_groups[group]
            if value > best_val:
                best_i, best_val, best_row = i, value, row

        if best_row is None:      # only the blocked piece is left — let it continue
            best_i, best_row = 0, remaining[0]
            best_val = best_row[0]

        base, aff, pop, card = best_row
        piece_id = card.get("piece_id") or (card.get("piece") or {}).get("id")
        group = _group_of(piece_id, piece_tags)
        seen_pieces[piece_id] += 1
        if group:
            seen_groups[group] += 1
        run_length = run_length + 1 if piece_id == run_piece else 1
        run_piece = piece_id
        card = {
            **card,
            "metadata": {
                **(card.get("metadata") or {}),
                "rec": {
                    "affinity": round(aff, 4),
                    "popularity": round(pop, 4),
                    "score": round(best_val, 4),
                },
            },
        }
        out.append(card)
        remaining.pop(best_i)
    return out
