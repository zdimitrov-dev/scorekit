""""More like this": cards similar to one specific card.

Distinct from ``scorekit.recommend``. The home feed ranks against accumulated taste; this
ranks against the single card being viewed. Opening a Birru performance should surface
more Birru whether or not Birru appears anywhere in the viewer's history.

Because the anchor is a card rather than a profile, none of this reads or writes the
user's taste vector, so browsing here cannot drag the home feed around.

Similarity has two halves. Tag overlap with the anchor's piece makes same-creator and
same-composer dominate. Title-word overlap recovers what tags cannot express: a
performer's repertoire is not part of a piece's tag set, so "Birru playing Laufey" and
another Laufey arrangement share no tag at all.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

from .recommend import affinity as tag_affinity

# How much of the score comes from words in the title rather than from tags. Kept a
# minority: tags are curated and reliable, titles are whatever an uploader typed.
TITLE_WEIGHT = 0.35

# A different card of the *same* piece is the most similar thing that exists — another
# recording of the very work you are looking at — so it gets a fixed lift.
SAME_PIECE_BONUS = 0.25

# Words that carry no information about what a piece is.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "by", "with", "from",
    "piano", "music", "sheet", "official", "video", "audio", "hd", "hq", "full", "live",
    "cover", "tutorial", "performance", "op", "no", "solo", "version", "remastered",
}


def _tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z0-9]+", text.lower())
            if len(w) > 2 and w not in _STOPWORDS}


def _title_overlap(a: set[str], b: set[str]) -> float:
    """Jaccard overlap — shared words divided by total distinct words.

    Dividing by the union rather than just counting matches stops a long, wordy title from
    looking similar to everything simply by containing more words.
    """
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similar_cards(
    anchor: dict[str, Any],
    cards: Iterable[dict[str, Any]],
    piece_tags: dict[str, list[tuple[str, str]]],
    weights: dict[tuple[str, str], float],
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Cards most like ``anchor``, best first. The anchor itself is never returned."""
    anchor_piece = anchor.get("piece_id") or (anchor.get("piece") or {}).get("id")
    anchor_tags = piece_tags.get(anchor_piece, [])
    anchor_words = _tokens(anchor.get("title") or "")

    # The anchor's own tags stand in for a taste profile, normalised the same way, so the
    # existing affinity maths can be reused unchanged.
    norm = sum(weights.get(t, 1.0) ** 2 for t in set(anchor_tags)) ** 0.5
    anchor_vector = {t: weights.get(t, 1.0) / norm for t in set(anchor_tags)} if norm else {}

    scored: list[tuple[float, dict[str, Any]]] = []
    for card in cards:
        if card.get("id") == anchor.get("id"):
            continue
        piece_id = card.get("piece_id") or (card.get("piece") or {}).get("id")
        tags = piece_tags.get(piece_id, [])

        score = (1 - TITLE_WEIGHT) * tag_affinity(tags, anchor_vector, weights)
        score += TITLE_WEIGHT * _title_overlap(anchor_words, _tokens(card.get("title") or ""))
        if piece_id and piece_id == anchor_piece:
            score += SAME_PIECE_BONUS
        if score > 0:
            scored.append((score, card))

    scored.sort(key=lambda row: -row[0])
    out = []
    for score, card in scored[:limit]:
        out.append({**card, "metadata": {**(card.get("metadata") or {}),
                                         "similarity": round(score, 4)}})
    return out
