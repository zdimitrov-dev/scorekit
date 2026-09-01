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

# Bump whenever scoring changes in a way that alters *which* cards are kept.
#
# Dropped cards are never stored, so a scoring fix cannot be applied by re-scoring what is
# in the database — the results it should now keep were thrown away at ingest and only a
# re-fetch can recover them. Stamping the version on every card lets the search cache spot
# results produced by superseded scoring and re-ingest that source instead of replaying
# them forever. Without it, a query searched before a fix keeps its old, worse results
# permanently: adding author matching fixed "Birru" for new queries while the already-
# cached "Birru" went on returning the single wrong card it had matched by title.
MATCHER_VERSION = 4


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


# Words that narrow the domain rather than naming anything. Searching "sook piano" is the
# same request as "sook" plus a hint about what kind of result is wanted, so these are
# stripped before matching. Leaving them in required the channel to be literally called
# "sook piano" and dropped 20 of that artist's 25 videos.
_QUALIFIERS = {
    "piano", "pianist", "keyboard", "music", "song", "songs", "cover", "covers",
    "tutorial", "tutorials", "official", "channel", "youtube", "playlist", "live",
    "hd", "hq", "full", "best", "top",
}


def _identity_tokens(q: list[str]) -> list[str]:
    """The part of a query that actually names something.

    Falls back to the whole query when nothing is left, so a bare "piano" still behaves
    as a search rather than matching everything.
    """
    core = [t for t in q if t not in _QUALIFIERS]
    return core or q


def _names_author(q: list[str], author: list[str]) -> bool:
    """True if the query reads as this author's name.

    Every query token must appear in the author **in order**, matching either a whole
    token or the start of one, so shortened and partial names work the way people
    actually type them: "Kat Cordova" names *Katherine Cordova*, "Rousseau" names
    *Rousseau*. Requiring an exact contiguous run instead dropped 11 of 12 correct
    results for that search.

    Domain words are stripped first (see ``_QUALIFIERS``): "sook piano" names the channel
    *sook*, and requiring "piano" to appear in the channel name too dropped 20 of that
    artist's 25 videos.

    Still strict enough to protect the filter: matching must be in order, and a prefix
    needs three characters, so "Piano Sonata" does not name a channel called "Piano
    Tutorials" and cannot rescue a card the title already rejected.
    """
    if not q or not author:
        return False
    q = _identity_tokens(q)
    i = 0
    for token in author:
        if i < len(q) and (token == q[i] or (len(q[i]) >= 3 and token.startswith(q[i]))):
            i += 1
    return i == len(q)


def _text_score(q: list[str], text: list[str]) -> float:
    """Blend *which* query words appear (overlap) with *how much of the query is
    reproduced in order* (longest contiguous run), the latter weighted higher because
    word order carries the phrase. A full-phrase hit scores 1.0."""
    if not text:
        return 0.0
    overlap = len(set(q) & set(text)) / len(set(q))
    run = _longest_run(q, text) / len(q)
    return 0.4 * overlap + 0.6 * run


def match_score(card: Card, query: str, composer: str | None = None) -> float:
    """Score in [0, 1] for how well ``card`` matches what was searched for.

    - **title**: the phrase blend above, so an exact hit outranks "Au clair de la lune",
      which has the words *clair/de/lune* but not the phrase.
    - **author**: a narrow escape hatch for queries that name an *artist* rather than a
      piece. Searching "Birru" returns that channel's uploads, whose titles never contain
      "Birru" — scoring titles alone gave all nine results 0.0 and the filter discarded a
      perfect result set. It counts **only when the whole query appears contiguously in
      the author**, so it cannot erode the filter's precision: a partial overlap with a
      channel name ("Piano Sonata" against a channel called "Piano Tutorials") is noise
      and is ignored, leaving the title the sole judge exactly as before.
    - **composer**: a boost when the composer surname appears in either field. For IMSLP
      the author *is* the composer, so this lifts the real work above same-name works by
      other composers — without dropping them.

    The blend is deliberately continuous rather than bucketed: a flat score makes the
    feed's "Best match" ordering degenerate into whatever the tiebreak is.
    """
    q = _tokens(query)
    if not q:
        return 0.0
    ct = _tokens(card.title or "")

    title = _text_score(q, ct)

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

    # All-or-nothing by design (see docstring): the query either names this artist or it
    # tells us nothing about them. Deliberately placed after the number rule — when the
    # query *is* the artist, opus numbers in their video titles are irrelevant.
    at = _tokens(card.author or "")
    author = 1.0 if _names_author(q, at) else 0.0
    base = max(title, author)

    composer_boost = 0.0
    if composer:
        toks = _tokens(composer)
        surname = toks[-1] if toks else ""
        hay = set(ct) | set(at)
        if surname and surname in hay:
            composer_boost = 0.3

    return round(min(1.0, base + composer_boost), 3)


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
        c.metadata = {
            **(c.metadata or {}),
            "match_score": s,
            "rank": rank,
            "mv": MATCHER_VERSION,
        }
        if s < drop_threshold:
            dropped += 1
            continue
        kept.append(c)
    return kept, dropped
