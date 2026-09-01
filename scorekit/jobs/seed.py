"""Seed the corpus from IMSLP's catalogue instead of waiting to be searched.

Ingestion is otherwise reactive: nothing enters the database until a user searches for it,
so the corpus mirrors previous searches. That caps the recommender twice. It can never
surprise anyone with a piece nobody thought to look up, and on a small corpus the IDF
statistics it weights tags by are computed from noise. Neither is fixed by more
interactions; both need more items.

IMSLP is the right source to seed from: no API quota (unlike YouTube's ~100 searches a
day), page titles carry the composer, and work pages carry the style and instrumentation
that make a piece rankable on arrival.

Seeding is composer-scoped, not category-scoped. ``Category:For piano`` holds 54,000+
pages ordered alphabetically, which yields mostly obscurity; a curated composer list
yields repertoire people recognise. Each composer's category is then filtered to piano
works, because it holds everything they wrote.

Only IMSLP cards are created. YouTube and MuseScore stay lazy, so seeding thousands of
pieces never touches the quota-limited sources.

    python -m scorekit.jobs.seed --dry-run
    python -m scorekit.jobs.seed --per-composer 15
"""
from __future__ import annotations

import argparse
import logging
import time

from ..connectors.base import ConnectorUnavailable
from ..connectors.imslp import ImslpConnector, _parse_title
from ..db import get_client
from ..models import Piece
from ..normalize import normalize_slug
from ..store import retag_piece, upsert_cards, upsert_piece
from ..tagging import _forms_in

log = logging.getLogger("scorekit.seed")


def _priority(page_title: str) -> tuple[int, int, str]:
    """Sort key putting recognisable repertoire first.

    A composer's category comes back alphabetically, which for Chopin means opening with
    "2 Mazurkas, B.16" rather than the Nocturnes — so a small ``--per-composer`` would seed
    the obscure end of every composer. Naming a musical form and carrying an opus number
    both track how well known a work is, and they cost nothing to read off the title.
    """
    named_form = bool(_forms_in(page_title))
    has_opus = "op." in page_title.lower()
    return (0 if named_form else 1, 0 if has_opus else 1, page_title)

# IMSLP category names, which are "Surname, Forename" exactly. Curated for recognisable
# piano repertoire across eras rather than scraped, so the seeded corpus opens with music
# people know instead of whatever sorts first alphabetically.
SEED_COMPOSERS = [
    # baroque
    "Bach, Johann Sebastian", "Handel, George Frideric", "Scarlatti, Domenico",
    "Rameau, Jean-Philippe", "Couperin, François", "Pachelbel, Johann",
    # classical
    "Mozart, Wolfgang Amadeus", "Haydn, Joseph", "Beethoven, Ludwig van",
    "Clementi, Muzio", "Czerny, Carl",
    # romantic
    "Chopin, Frédéric", "Liszt, Franz", "Schumann, Robert", "Schubert, Franz",
    "Brahms, Johannes", "Mendelssohn, Felix", "Tchaikovsky, Pyotr",
    "Grieg, Edvard", "Rachmaninoff, Sergei", "Scriabin, Aleksandr",
    "Field, John", "Fauré, Gabriel", "Albéniz, Isaac", "Granados, Enrique",
    # impressionist / modern
    "Debussy, Claude", "Ravel, Maurice", "Satie, Erik", "Prokofiev, Sergey",
    "Shostakovich, Dmitry", "Bartók, Béla", "Joplin, Scott", "Gershwin, George",
]

# IMSLP is a volunteer-run archive and this walks a lot of pages, so pace the requests.
REQUEST_DELAY_S = 0.35


def _existing_slugs(sb) -> set[str]:
    """Slugs already stored, so a re-run skips what it has and stays cheap."""
    slugs: set[str] = set()
    seen = 0
    while True:
        rows = sb.table("pieces").select("slug").range(seen, seen + 999).execute().data or []
        slugs.update(r["slug"] for r in rows)
        seen += len(rows)
        if len(rows) < 1000:
            return slugs


def seed_composer(
    connector: ImslpConnector,
    composer_category: str,
    per_composer: int,
    existing: set[str],
    enrich: bool = True,
    dry_run: bool = False,
) -> int:
    """Seed up to ``per_composer`` piano works by one composer. Returns how many landed."""
    category = composer_category if composer_category.startswith("Category:") \
        else f"Category:{composer_category}"
    try:
        titles = connector.category_members(category)
    except Exception as exc:
        log.warning("  ! %s: could not list category (%s)", composer_category, exc)
        return 0
    if not titles:
        log.warning("  ! %s: no such category, or empty", composer_category)
        return 0

    piano = sorted(connector.piano_titles(titles), key=_priority)
    log.info("  %s: %d works, %d for piano", composer_category, len(titles), len(piano))

    added = 0
    for page_title in piano:
        if added >= per_composer:
            break
        title, composer = _parse_title(page_title)
        slug = normalize_slug(title, composer)
        if slug in existing:
            continue

        card = connector.card_for_page(page_title)
        if card is None:
            continue
        if enrich:
            try:
                card = connector.enrich(card)
            except Exception as exc:   # one bad page must not end the run
                log.debug("    enrich failed for %s: %s", page_title, exc)
        if dry_run:
            log.info("    [dry-run] %s — %s", title, composer or "?")
        else:
            piece_id = upsert_piece(Piece(slug=slug, title=title, composer=composer))
            upsert_cards(piece_id, [card])
            retag_piece(piece_id)
        existing.add(slug)
        added += 1
        time.sleep(REQUEST_DELAY_S)
    return added


def seed(
    composers: list[str] | None = None,
    per_composer: int = 15,
    budget: int | None = None,
    enrich: bool = True,
    dry_run: bool = False,
) -> int:
    connector = ImslpConnector()
    sb = get_client()
    existing = set() if dry_run else _existing_slugs(sb)
    log.info("%d pieces already stored", len(existing))

    total = 0
    for composer in composers or SEED_COMPOSERS:
        remaining = per_composer if budget is None else min(per_composer, budget - total)
        if remaining <= 0:
            break
        total += seed_composer(connector, composer, remaining, existing, enrich, dry_run)
        log.info("  running total: %d", total)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the corpus from IMSLP's catalogue.")
    parser.add_argument("--composers", nargs="*", help="IMSLP category names to seed from")
    parser.add_argument("--per-composer", type=int, default=15)
    parser.add_argument("--budget", type=int, help="stop after this many pieces in total")
    parser.add_argument("--no-enrich", action="store_true", help="skip work-page enrichment")
    parser.add_argument("--dry-run", action="store_true", help="print what would be seeded")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        total = seed(
            composers=args.composers,
            per_composer=args.per_composer,
            budget=args.budget,
            enrich=not args.no_enrich,
            dry_run=args.dry_run,
        )
    except ConnectorUnavailable as exc:
        raise SystemExit(str(exc))
    log.info("\n%s%d pieces seeded", "[dry-run] " if args.dry_run else "", total)


if __name__ == "__main__":
    main()
