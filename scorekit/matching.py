"""Attribution matching — score how well a card matches the queried piece.

Search (YouTube or IMSLP) returns loose, name-colliding results: a query for
Debussy's "Clair de lune" also pulls the "Au clair de la lune" folk song, pop
songs, and game soundtracks that merely share the words. Attaching all of them to
one ``piece_id`` pollutes the recommender's signal.

This scores each card against the intended piece and **drops only clear
non-matches**, deliberately KEEPING borderline / lesser works (a soft narrow, not
a hard exact-match filter) so a user can still discover a smaller related piece.
The score is stored on every card (``metadata['match_score']``) so the feed and
recommender can rank by it rather than relying on the drop alone.

Known residual: on YouTube we cannot tell a piano cover of Debussy's piece from a
*different* composition that happens to share the exact title (e.g. the Flight
Facilities pop song "Clair de Lune") — both have the phrase and no composer tag.
Those keep a high score by design; separating them needs audio/semantic analysis.
"""
from __future__ import annotations

import re
import unicodedata

from .models import Card

# Below this, a card is treated as clearly not the queried piece and dropped.
# Kept deliberately lenient: narrow out obvious noise (little/no title overlap)
# without excluding lesser or related works, which survive at a lower score.
DROP_THRESHOLD = 0.35


def _tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", text.lower())


def _contiguous(needle: list[str], haystack: list[str]) -> bool:
    """True if ``needle`` appears as a contiguous run of tokens in ``haystack``."""
    if not needle or len(needle) > len(haystack):
        return False
    return any(
        haystack[i:i + len(needle)] == needle
        for i in range(len(haystack) - len(needle) + 1)
    )


def match_score(card: Card, query: str, composer: str | None = None) -> float:
    """Score in [0, 1] for how well ``card`` matches the intended piece.

    - **title**: 1.0 if the query title appears as a contiguous phrase in the card
      title; otherwise partial credit for token overlap. So an exact hit outscores
      "Au clair de la lune" (which has the words *clair/de/lune* but not the phrase).
    - **composer**: a boost when the composer surname appears in the card title or
      author. For IMSLP the author *is* the composer, so this reliably lifts the
      real work above same-name works by other composers — without dropping them.
    """
    q = _tokens(query)
    if not q:
        return 0.0
    ct = _tokens(card.title or "")

    if _contiguous(q, ct):
        title = 1.0
    else:
        overlap = len(set(q) & set(ct)) / len(set(q))
        title = 0.5 * overlap

    # Opus / movement numbers are highly distinctive: a query number missing from the
    # card usually means a *different* work ("Op 48 No 1" vs "Op 68 No 1"), while common
    # words (op, no, in) match everything. Scale the title score by how many of the
    # query's numbers the card actually has.
    q_nums = {t for t in q if t.isdigit()}
    if q_nums:
        c_nums = {t for t in ct if t.isdigit()}
        num_frac = len(q_nums & c_nums) / len(q_nums)
        title *= 0.3 + 0.7 * num_frac

    composer_boost = 0.0
    if composer:
        toks = _tokens(composer)
        surname = toks[-1] if toks else ""
        hay = set(ct) | set(_tokens(card.author or ""))
        if surname and surname in hay:
            composer_boost = 0.3

    return round(min(1.0, title + composer_boost), 3)


def annotate_and_filter(
    cards: list[Card],
    query: str,
    composer: str | None = None,
    drop_threshold: float = DROP_THRESHOLD,
) -> tuple[list[Card], int]:
    """Score every card into ``metadata['match_score']`` and drop those below
    ``drop_threshold``. Returns ``(kept_cards, dropped_count)``."""
    kept: list[Card] = []
    dropped = 0
    for c in cards:
        s = match_score(c, query, composer)
        c.metadata = {**(c.metadata or {}), "match_score": s}
        if s < drop_threshold:
            dropped += 1
            continue
        kept.append(c)
    return kept, dropped
