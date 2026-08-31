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


def _longest_run(needle: list[str], haystack: list[str]) -> int:
    """Length of the longest contiguous run of ``needle`` tokens inside ``haystack``.

    Graded version of a phrase check: the full query matching end-to-end returns
    ``len(needle)``, while a partial phrase still earns proportional credit. This is
    what separates "Chopin Nocturne **Op 48 No 1**" (run of 4) from a title that
    merely shares the same words scattered around.
    """
    best = 0
    for i in range(len(needle)):
        for j in range(len(haystack)):
            k = 0
            while (
                i + k < len(needle)
                and j + k < len(haystack)
                and needle[i + k] == haystack[j + k]
            ):
                k += 1
            best = max(best, k)
    return best


def match_score(card: Card, query: str, composer: str | None = None) -> float:
    """Score in [0, 1] for how well ``card`` matches the intended piece.

    - **title**: blends *which* query words the card has (overlap) with *how much of
      the query it reproduces in order* (longest contiguous run), the latter weighted
      higher because word order carries the phrase. A full-phrase hit scores 1.0 and
      outranks "Au clair de la lune", which has the words but not the phrase.
    - **composer**: a boost when the composer surname appears in the card title or
      author. For IMSLP the author *is* the composer, so this reliably lifts the
      real work above same-name works by other composers — without dropping them.

    The blend is deliberately continuous rather than bucketed: a flat score makes the
    feed's "Best match" ordering degenerate into whatever the tiebreak is.
    """
    q = _tokens(query)
    if not q:
        return 0.0
    ct = _tokens(card.title or "")

    overlap = len(set(q) & set(ct)) / len(set(q))
    run = _longest_run(q, ct) / len(q)
    title = 0.4 * overlap + 0.6 * run

    # Opus / movement numbers are the most distinctive tokens in a classical title,
    # while the words around them (op, no, in) match everything. What matters is
    # *contradiction*, not mere absence:
    #   - the card names a different opus ("Op.68 No.1" for a query of Op 48) — it is
    #     a different work, so penalise hard.
    #   - the card names no number at all ("Nocturne in C minor") — it may well be the
    #     same piece described by key instead, so only penalise mildly.
    q_nums = {t for t in q if t.isdigit()}
    if q_nums:
        c_nums = {t for t in ct if t.isdigit()}
        if not c_nums:
            title *= 0.6
        else:
            matched = len(q_nums & c_nums) / len(q_nums)
            title *= 0.1 + 0.9 * matched

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
    ``drop_threshold``. Returns ``(kept_cards, dropped_count)``.

    ``cards`` arrives in the connector's own relevance order, which is signal we would
    otherwise throw away, so each card also keeps its 0-based ``metadata['rank']``. The
    feed uses it to break match_score ties without falling back on view count (which
    would make "Best match" and "Most viewed" produce the same ordering).
    """
    kept: list[Card] = []
    dropped = 0
    for rank, c in enumerate(cards):
        s = match_score(c, query, composer)
        c.metadata = {**(c.metadata or {}), "match_score": s, "rank": rank}
        if s < drop_threshold:
            dropped += 1
            continue
        kept.append(c)
    return kept, dropped
