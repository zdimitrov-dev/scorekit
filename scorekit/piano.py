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
    r"\b(?:piano|pianos|pianist|pianists|klavier|clavier|harpsichord|"
    r"synthesia|flowkey|musicnotes|pianote|4[- ]hands|piano solo)\b"
)

# A different instrument is the subject. Decisive: naming one of these in a title is
# almost never compatible with a piano performance. Checked only after the piano evidence,
# so a piano transcription still survives its own title.
_OTHER_INSTRUMENT_RE = re.compile(
    r"\b(?:violin\w*|geige\w*|cello\w*|violoncell\w*|viola|guitar\w*|gitarre\w*|"
    r"flute|fl\u00f6te|clarinet\w*|oboe|bassoon|trumpet\w*|trombone|saxophon\w*|sax|"
    r"harp|drums|drummer|percussion|organist|acapella|a cappella)\b"
)

# Ensemble and vocal words, which are weaker evidence because they show up in the names of
# pieces and songs as often as in descriptions of who is playing. "i hear a symphony if
# liszt composed it" is a solo piano cover of a song called "I Hear a Symphony". These
# reject an unknown upload, but a channel already shown to be a piano channel overrides
# them; a named instrument it never does.
_ENSEMBLE_RE = re.compile(
    r"\b(?:orchestra|orchestral|symphony|symphonie|sinfonie|philharmonic|"
    r"string quartet|quartet|choir|chorus|choral|opera|operatic|"
    r"vocal|vocals|singer|band)\b"
)

# Not music at all. Kept separate from the instrument list because it is decisive: no
# amount of piano-adjacent wording redeems a lecture about Rousseau the philosopher.
_NON_MUSIC_RE = re.compile(
    r"\b(?:lecture|lectures|philosophy|philosopher|political theory|politics|"
    r"documentary|biography|audiobook|podcast|interview|explained|"
    r"unboxing|review|reviews|gameplay|walkthrough|vlog|recipe|workout|"
    r"mechanical keyboard|keycaps|keyboards|switches|gaming|laptop|"
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


# Forms that essentially only exist for solo piano. Concerto, sonata and symphony are
# deliberately absent: every instrument has them, and "violin concerto Bruch" was
# qualifying as piano repertoire on the word "concerto" alone.
_PIANO_FORMS = {
    "nocturne", "prelude", "etude", "mazurka", "polonaise", "ballade", "scherzo",
    "impromptu", "gymnopedie", "invention", "arabesque", "waltz", "rag", "intermezzo",
}


def _is_piano_repertoire(query: str, composer: str | None) -> bool:
    """Does the *piece* being ingested belong to the piano canon?

    The fallback for results that describe themselves in neither direction. A search for
    "Chopin Nocturne Op 9 No 2" is piano repertoire whatever any individual video says, so
    an unlabelled result from that search is far more likely piano than not — while the
    same silence on a "Taylor Swift" search means nothing of the kind.
    """
    text = f"{composer or ''} {query}"
    tokens = set(re.findall(r"[a-z]+", _norm(text)))
    if tokens & set(_COMPOSER_ERA):
        return True
    return bool(_forms_in(text) & _PIANO_FORMS)


def is_piano(card: Card, query: str = "", composer: str | None = None) -> bool:
    """True if this YouTube card should enter the corpus."""
    claims = _claims_text(card)
    if not claims:
        return False

    # 1. The title or channel names another instrument, and does not name a piano.
    #    Ahead of the piano evidence below because a concert blurb mentions a piano often
    #    enough to rescue an orchestral violin concerto from its own title. Requiring the
    #    absence of "piano" matters: The Piano Guys are a piano and cello duo, and
    #    rejecting on "cello" alone lost half their catalogue.
    if _OTHER_INSTRUMENT_RE.search(claims) and not _PIANO_RE.search(claims):
        return False
    # 2. Says it is piano, anywhere, description included. Ahead of the *ensemble* words
    #    below, so Kassia's "Beethoven - Symphony No. 5" survives its own title: it is a
    #    Liszt piano transcription and only the description says so.
    if _PIANO_RE.search(_all_text(card)):
        return True
    # 3. Declares itself something else, read from the title and channel only.
    if _NON_MUSIC_RE.search(claims) or _ENSEMBLE_RE.search(claims):
        return False
    # 4. Silent either way: trust what the piece is.
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
        # A proven piano channel vouches for its other uploads, overriding the ensemble
        # words but never a named instrument: a pianist posting a song called "I Hear a
        # Symphony" is ordinary, a pianist posting a violin concerto is not.
        or (c.author and _norm(c.author) in channels
            and not _NON_MUSIC_RE.search(_claims_text(c))
            and not _OTHER_INSTRUMENT_RE.search(_claims_text(c)))
    ]
    return kept, len(cards) - len(kept)
