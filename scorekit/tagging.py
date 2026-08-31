"""Feature extraction — derive ``piece_tags`` rows from a piece and its cards.

These tags are the feature space the **content-based recommender** ranks over
(``scorekit/recommend.py``). Keeping extraction here, separate from both the
connectors that fetch data and the ranker that consumes it, means the tag vocabulary
can change without touching either.

Why tags are derived at the **piece** level: enrichment is uneven across sources. A
YouTube card knows almost nothing about the music, while one IMSLP card carries style,
instrumentation and licensing. Because every card for the same real piece shares a
``piece_id``, a single enriched card lets us tag the piece — and every card attached to
it, including the bare YouTube ones, becomes rankable. This is exactly what the shared
``piece_id`` normalization was built for.

Tag keys currently produced:

``composer``        the composing artist (IMSLP's ``author`` is authoritative)
``era``             baroque / classical / romantic / impressionist / modern
``style``           IMSLP's own ``piece_style`` string, kept verbatim-ish
``instrumentation`` piano / organ / voice, piano / ...
``form``            nocturne / prelude / sonata / ... — inferred from titles
``public_domain``   "true" when a free score exists

Values are lowercased and whitespace-collapsed so that "Organ" and "organ" are one tag.

**Only high-confidence cards define a piece's identity.** The attribution filter keeps
loosely-related neighbours on purpose (a soft narrow, so a smaller related work is still
discoverable), but those neighbours must not describe the piece: deriving from every card
tagged Debussy's "Clair de lune" as a *rag* and Beethoven's "Moonlight Sonata" with the
composer of a guitar arrangement of it. Identity tags therefore come from cards scoring
at least ``CONFIDENT_MATCH``, falling back to all cards only when none qualify.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any, Iterable

# A card must match the piece at least this well to describe it. Above the lenient
# DROP_THRESHOLD in matching.py: good enough to *show* is not good enough to *define*.
CONFIDENT_MATCH = 0.8

# Musical form / genre cues, matched as whole words against piece and card titles.
# Ordered most-specific first so "prelude and fugue" does not register only as "fugue".
_FORMS: tuple[tuple[str, str], ...] = (
    ("nocturne", r"nocturnes?|notturno"),
    ("prelude", r"preludes?|pr[ée]lude"),
    ("fugue", r"fugues?"),
    ("sonata", r"sonatas?|sonate"),
    ("etude", r"[ée]tudes?|etudes?"),
    ("waltz", r"waltz(?:es)?|valse"),
    ("mazurka", r"mazurkas?"),
    ("polonaise", r"polonaises?"),
    ("ballade", r"ballades?"),
    ("scherzo", r"scherzos?|scherzi"),
    ("impromptu", r"impromptus?"),
    ("rhapsody", r"rhapsod(?:y|ies)|rapsodie"),
    ("concerto", r"concertos?|konzert"),
    ("symphony", r"symphon(?:y|ies)|symphonie"),
    ("suite", r"suites?"),
    ("variations", r"variations?"),
    ("canon", r"canons?|kanon"),
    ("gymnopedie", r"gymnop[ée]dies?"),
    ("invention", r"inventions?"),
    ("toccata", r"toccatas?"),
    ("intermezzo", r"intermezzi?o?s?"),
    ("march", r"marche?s?"),
    ("minuet", r"minuets?|menuet"),
    ("arabesque", r"arabesques?"),
    ("rag", r"rags?|ragtime"),
)

# Composer surname -> era, for pieces with no IMSLP style to read it off. Deliberately
# small and explicit rather than a date heuristic: a wrong era is worse than no tag,
# because it silently biases every recommendation built on it.
_COMPOSER_ERA: dict[str, str] = {
    "bach": "baroque", "handel": "baroque", "vivaldi": "baroque",
    "scarlatti": "baroque", "pachelbel": "baroque", "buxtehude": "baroque",
    "couperin": "baroque", "rameau": "baroque", "krebs": "baroque",
    "mozart": "classical", "haydn": "classical", "clementi": "classical",
    "beethoven": "classical",   # transitional; catalogued as classical
    "chopin": "romantic", "liszt": "romantic", "schumann": "romantic",
    "schubert": "romantic", "brahms": "romantic", "mendelssohn": "romantic",
    "tchaikovsky": "romantic", "grieg": "romantic", "rachmaninoff": "romantic",
    "rachmaninov": "romantic", "scriabin": "romantic", "faure": "romantic",
    "debussy": "impressionist", "ravel": "impressionist", "satie": "impressionist",
    "prokofiev": "modern", "shostakovich": "modern", "bartok": "modern",
    "stravinsky": "modern", "glass": "modern", "einaudi": "modern",
    "gershwin": "modern", "joplin": "modern",
}

# IMSLP's piece_style vocabulary -> our era values.
_STYLE_ERA: dict[str, str] = {
    "baroque": "baroque",
    "classical": "classical",
    "romantic": "romantic",
    "impressionist": "impressionist",
    "early 20th century": "modern",
    "modern": "modern",
    "20th century": "modern",
    "21st century": "modern",
    "renaissance": "renaissance",
    "medieval": "medieval",
}


# Canonical instruments, matched as whole words against IMSLP's free-text
# instrumentation — which ranges from "piano" to an entire orchestral roster with HTML
# tags embedded in it. A small controlled vocabulary is a far better feature than the raw
# string, which is essentially never comparable between two pieces.
_INSTRUMENTS: tuple[tuple[str, str], ...] = (
    ("piano", r"pianos?|klavier"),
    ("organ", r"organs?"),
    ("harpsichord", r"harpsichords?|cembalo"),
    ("guitar", r"guitars?|lyre guitar"),
    ("violin", r"violins?"),
    ("viola", r"violas?"),
    ("cello", r"(?:violon)?cellos?"),
    ("voice", r"voices?|soprano|alto|tenor|baritone|choir|chorus"),
    ("flute", r"flutes?"),
    ("clarinet", r"clarinets?"),
    ("oboe", r"oboes?"),
    ("bassoon", r"bassoons?"),
    ("trumpet", r"trumpets?"),
    ("horn", r"horns?"),
    ("harp", r"harps?"),
    ("orchestra", r"orchestras?|strings|timpani|continuo"),
)


def _norm(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace — the canonical tag value form."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def _surname(composer: str) -> str:
    """Last alphabetic token of a composer name — "Claude Debussy" -> "debussy".

    IMSLP also writes "Debussy, Claude"; the comma form is handled by taking the part
    before the comma, so both spellings collapse to the same key.
    """
    name = _norm(composer)
    if "," in name:
        name = name.split(",", 1)[0]
    parts = [p for p in re.findall(r"[a-z]+", name) if p]
    return parts[-1] if parts else ""


def _forms_in(text: str) -> set[str]:
    """Musical forms named in ``text`` (whole-word matches)."""
    t = _norm(text)
    return {form for form, pattern in _FORMS if re.search(rf"\b(?:{pattern})\b", t)}


def _instruments_in(text: str) -> set[str]:
    """Canonical instruments named in a free-text instrumentation string."""
    t = _norm(re.sub(r"<[^>]+>", " ", text or ""))   # IMSLP embeds HTML in this field
    return {name for name, pattern in _INSTRUMENTS if re.search(rf"\b(?:{pattern})\b", t)}


def _confident(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The cards trustworthy enough to *define* the piece, not merely to be shown with it.

    Falls back to every card when nothing clears the bar, so a piece whose cards all
    scored modestly still gets tagged rather than silently dropping out of the feature
    space entirely.
    """
    strong = [
        c for c in cards
        if ((c.get("metadata") or {}).get("match_score") or 0) >= CONFIDENT_MATCH
    ]
    return strong or cards


def _corroborated(votes: Counter[str], min_votes: int = 2) -> Counter[str]:
    """Keep only values more than one card agrees on.

    Falls back to the single-vote values when *nothing* is corroborated, so a piece with
    only one enriched card is still described rather than left featureless.
    """
    agreed = Counter({v: n for v, n in votes.items() if n >= min_votes})
    return agreed or votes


def _infer_composer(piece: dict[str, Any], cards: list[dict[str, Any]]) -> str | None:
    """Best guess at the composing artist when the piece row doesn't name one.

    Two independent votes, because each fails differently:

    - **Known composer surnames in card titles.** High precision (the vocabulary is a
      curated list, so "Chopin" in a video title is really Chopin) and robust, since
      dozens of cards vote. This is what rescues "Moonlight Sonata" -> Beethoven.
    - **IMSLP ``author``.** Authoritative for an original work, but on a *derivative* it
      names the arranger — which is how "Moonlight Sonata" first came out as the composer
      of a guitar transcription of it.

    The piece's own title is taken on trust when it names a composer, since that is what
    was actually searched for. Otherwise a name must appear on **two** cards: a single
    incidental mention is not evidence, and an artist search for "Birru" was assigned
    Liszt off one video called "i hear a symphony if liszt composed it". No confident
    answer means no tag — a wrong composer is worse than a missing one, because every era
    and similarity judgement is built on it.
    """
    if piece.get("composer"):
        return piece["composer"]

    in_title = [
        t for t in re.findall(r"[a-z]+", _norm(piece.get("title") or ""))
        if t in _COMPOSER_ERA
    ]
    if in_title:
        return in_title[0]

    # One merged tally: a name carried by a card title *and* an IMSLP author is two
    # independent pieces of evidence, and siloing them meant Debussy — named once each
    # way — cleared neither bar. Only IMSLP authors are counted; a YouTube channel is the
    # performer, and tagging it as the composer would poison the feature outright.
    votes: Counter[str] = Counter()
    for c in cards:
        for token in set(re.findall(r"[a-z]+", _norm(c.get("title") or ""))):
            if token in _COMPOSER_ERA:
                votes[token] += 1
        if c.get("source") == "imslp" and c.get("author"):
            votes[_surname(c["author"])] += 1

    if votes:
        name, count = votes.most_common(1)[0]
        if count >= 2:
            return name
    return None


def derive_tags(piece: dict[str, Any], cards: Iterable[dict[str, Any]]) -> set[tuple[str, str]]:
    """Return the ``(key, value)`` tag set for one piece, given its cards.

    Pure and side-effect free so it can be unit-tested and re-run over the whole corpus
    whenever the vocabulary changes.
    """
    cards = list(cards)
    strong = _confident(cards)
    tags: set[tuple[str, str]] = set()

    # --- composer -----------------------------------------------------------
    # Voted across all cards: the more titles, the steadier the vote.
    composer = _infer_composer(piece, cards)
    surname = _surname(composer) if composer else ""
    if surname:
        tags.add(("composer", surname))

    # A work is described by what its cards *agree* on. A single card is usually an
    # arrangement rather than the work: one ragtime cover of "Clair de lune" tagged the
    # piece a rag, and one orchestral transcription tagged "Für Elise" an orchestral work.
    styles: Counter[str] = Counter()
    instruments: Counter[str] = Counter()
    forms: Counter[str] = Counter()
    for c in strong:
        meta = c.get("metadata") or {}
        if meta.get("piece_style"):
            styles[_norm(str(meta["piece_style"]))] += 1
        instruments.update(_instruments_in(str(meta.get("instrumentation") or "")))
        forms.update(_forms_in(c.get("title") or ""))

    # --- era ----------------------------------------------------------------
    # The curated composer table is preferred over IMSLP's own `piece_style`, which is
    # both coarser ("Early 20th century" for Debussy, where "impressionist" is the useful
    # distinction) and aggregated over cards that may not all be this piece.
    era = _COMPOSER_ERA.get(surname) if surname else None
    for style, _n in _corroborated(styles).most_common():
        tags.add(("style", style))
        if era is None:
            era = _STYLE_ERA.get(style)
    if era:
        tags.add(("era", era))

    # --- instrumentation ----------------------------------------------------
    for instrument in _corroborated(instruments):
        tags.add(("instrumentation", instrument))

    # --- form ---------------------------------------------------------------
    # What the piece title itself says is taken on trust — it is the work's own name.
    for form in _forms_in(piece.get("title") or "") | set(_corroborated(forms)):
        tags.add(("form", form))

    # --- creator ------------------------------------------------------------
    # When one channel accounts for most of a piece's videos, that channel *is* what the
    # entry is about — an artist search ("Patrik Pietschmann") produces exactly this. Such
    # a piece has no composer, era or form to speak of, so without this it carries no
    # features at all and is invisible to the recommender no matter how often it is liked.
    # Requires dominance, so a piece with a normal spread of performers gets no creator.
    channels = Counter(
        _norm(c["author"]) for c in cards
        if c.get("source") == "youtube" and c.get("author")
    )
    if channels:
        name, count = channels.most_common(1)[0]
        if count >= 3 and count / sum(channels.values()) >= 0.5:
            tags.add(("creator", name))

    # --- licensing ----------------------------------------------------------
    if any((c.get("metadata") or {}).get("is_public_domain") for c in strong):
        tags.add(("public_domain", "true"))

    return tags


def tag_rows(piece_id: str, tags: Iterable[tuple[str, str]]) -> list[dict[str, str]]:
    """Shape a tag set into ``piece_tags`` rows."""
    return [{"piece_id": piece_id, "key": k, "value": v} for k, v in sorted(tags)]
