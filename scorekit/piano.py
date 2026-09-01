"""Is this YouTube result actually piano music?

scorekit is a piano platform, but YouTube search is not: a query like "Rousseau" returns
that pianist's covers alongside political-philosophy lectures. Anything let through lands
in the corpus permanently and then feeds the recommender.

Only YouTube needs this. IMSLP is filtered at the catalogue level by instrument category,
and MuseScore results are sheet music by construction.

Matching the word "piano" alone fails in both directions, and two real results prove it:
"Chopin - Nocturne op.9 No.2" never says piano anywhere, while Kassia's "Beethoven -
Symphony No. 5" is a Liszt piano transcription. So the evidence is layered, strongest
first, and only the last layer falls back to what the piece is rather than what the video
says about itself.
"""
from __future__ import annotations

import re

from .models import Card
from .tagging import _COMPOSER_ERA, _forms_in, _norm

# Direct evidence that the video is piano: the instrument, a player, or the tooling that
# only ever surrounds piano content (Synthesia is a piano-roll visualiser; flowkey and
# musicnotes sell piano arrangements).
_PIANO_RE = re.compile(
    r"\b(?:piano|pianos|pianist|pianists|klavier|clavier|keyboard|harpsichord|"
    r"synthesia|flowkey|musicnotes|pianote|4[- ]hands|piano solo)\b"
)

# Another instrument or ensemble is the subject. Checked only *after* the piano evidence,
# because a piano transcription of a symphony legitimately says "symphony".
_OTHER_INSTRUMENT_RE = re.compile(
    r"\b(?:violin|violins|violinist|cello|cellist|viola|guitar|guitarist|flute|clarinet|"
    r"oboe|bassoon|trumpet|trombone|saxophone|sax|harp|drums|drummer|percussion|"
    r"orchestra|orchestral|symphony|symphonie|sinfonie|philharmonic|string quartet|"
    r"quartet|choir|chorus|choral|opera|operatic|vocal|vocals|singer|acapella|"
    r"a cappella|band|organist)\b"
)

# Not music at all. Kept separate from the instrument list because it is decisive: no
# amount of piano-adjacent wording redeems a lecture about Rousseau the philosopher.
_NON_MUSIC_RE = re.compile(
    r"\b(?:lecture|lectures|philosophy|philosopher|political theory|politics|"
    r"documentary|biography|audiobook|podcast|interview|explained|"
    r"unboxing|review|reviews|gameplay|walkthrough|vlog|recipe|workout|"
    r"tutorial for beginners in (?:python|java)|programming)\b"
)


def _claims_text(card: Card) -> str:
    """Title and channel — what the video declares itself to be.

    Rejection reads only this. Descriptions are promotional copy full of incidental
    mentions, and matching them cost real results: a pianist's bio named the orchestras he
    plays with, so "philharmonic" dropped his solo Grieg recital.
    """
    return _norm(" ".join(filter(None, [card.title, card.author])))


def _all_text(card: Card) -> str:
    """Everything, description included. Acceptance reads this, because a description is
    where piano evidence legitimately hides — sheet-music links, "played on piano",
    flowkey and Synthesia referrals."""
    meta = card.metadata or {}
    return " ".join(filter(None, [
        _claims_text(card),
        _norm(str(meta.get("description_excerpt") or "")),
    ]))


def _is_piano_repertoire(query: str, composer: str | None) -> bool:
    """Does the *piece* being ingested belong to the piano canon?

    The fallback for results that describe themselves in neither direction. A search for
    "Chopin Nocturne Op 9 No 2" is piano repertoire whatever any individual video says, so
    an unlabelled result from that search is far more likely piano than not — while the
    same silence on a "Taylor Swift" search means nothing of the kind.
    """
    text = f"{composer or ''} {query}"
    tokens = set(re.findall(r"[a-z]+", _norm(text)))
    return bool(tokens & set(_COMPOSER_ERA)) or bool(_forms_in(text))


def is_piano(card: Card, query: str = "", composer: str | None = None) -> bool:
    """True if this YouTube card should enter the corpus."""
    claims = _claims_text(card)
    if not claims:
        return False

    # 1. Says it is piano — anywhere, description included. Deliberately ahead of the
    #    rejection rules: Kassia's "Beethoven - Symphony No. 5" is a Liszt piano
    #    transcription and only its description says so.
    if _PIANO_RE.search(_all_text(card)):
        return True
    # 2. Declares itself something else — read from the title and channel only.
    if _NON_MUSIC_RE.search(claims) or _OTHER_INSTRUMENT_RE.search(claims):
        return False
    # 3. Silent either way: trust what the piece is.
    return _is_piano_repertoire(query, composer)


def _piano_channels(cards: list[Card]) -> set[str]:
    """Channels that proved themselves piano channels within this result set.

    An artist search returns one channel's back catalogue, and a piano channel does not
    restate the instrument on every upload — Birru's "clair de lune but it's 3am" says
    nothing about a piano, though the channel plainly is one. Judging each card alone would
    keep the uploads that happen to mention it and discard the rest of the same channel.

    Two cards are required, so a single incidental mention on an otherwise unrelated
    channel does not vouch for its whole catalogue.
    """
    hits: dict[str, int] = {}
    for card in cards:
        if card.author and _PIANO_RE.search(_all_text(card)):
            name = _norm(card.author)
            hits[name] = hits.get(name, 0) + 1
    return {name for name, n in hits.items() if n >= 2}


def filter_piano(cards: list[Card], query: str = "", composer: str | None = None
                 ) -> tuple[list[Card], int]:
    """Drop non-piano cards. Returns ``(kept, dropped)``."""
    channels = _piano_channels(cards)
    kept = [
        c for c in cards
        if is_piano(c, query, composer)
        # a channel this result set has already shown to be a piano channel, provided
        # this particular upload isn't declaring itself something else
        or (c.author and _norm(c.author) in channels
            and not _NON_MUSIC_RE.search(_claims_text(c))
            and not _OTHER_INSTRUMENT_RE.search(_claims_text(c)))
    ]
    return kept, len(cards) - len(kept)
