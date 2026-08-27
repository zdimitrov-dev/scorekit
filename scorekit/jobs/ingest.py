"""Ingestion job — runs every connector for a query and upserts the results.

Runs each registered connector for a piece query, normalizes everything into
``Card`` objects, and (unless ``--dry-run``) upserts the piece (by slug) and its
cards into Supabase. Connectors that are not built yet — or that are built but
unconfigured (e.g. a missing API key) — are skipped with a warning rather than
failing the whole run.

    python -m scorekit.jobs.ingest --query "Clair de Lune"
    python -m scorekit.jobs.ingest --query "Clair de Lune" --composer Debussy
    python -m scorekit.jobs.ingest --query "Clair de Lune" --dry-run
"""
from __future__ import annotations

import argparse
import logging

from ..connectors import CONNECTORS
from ..connectors.base import ConnectorUnavailable
from ..models import Card, Piece
from ..normalize import normalize_slug
from ..store import upsert_cards, upsert_piece

log = logging.getLogger("scorekit.ingest")


def ingest(query: str, composer: str | None = None, limit: int = 20,
           store: bool = True) -> list[Card]:
    slug = normalize_slug(query, composer)
    log.info("Ingesting query=%r composer=%r -> slug=%r", query, composer, slug)

    cards: list[Card] = []
    for connector_cls in CONNECTORS:
        connector = connector_cls()
        try:
            found = connector.search(query, limit=limit)
        except (NotImplementedError, ConnectorUnavailable) as exc:
            log.warning("[%s] skipped: %s", connector.source, exc)
            continue
        log.info("[%s] returned %d card(s)", connector.source, len(found))
        cards.extend(found)

    if store:
        if cards:
            piece_id = upsert_piece(Piece(slug=slug, title=query, composer=composer))
            written = upsert_cards(piece_id, cards)
            log.info("Persisted piece %r (%s) with %d card(s).", slug, piece_id, written)
        else:
            log.info("No cards collected; nothing persisted.")
    return cards


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a scorekit ingestion.")
    parser.add_argument("--query", required=True, help="Piece to search for.")
    parser.add_argument("--composer", default=None, help="Optional composer hint.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true",
                        help="Collect and report only; do not write to Supabase.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(levelname)s %(name)s: %(message)s",
    )
    cards = ingest(args.query, composer=args.composer, limit=args.limit,
                   store=not args.dry_run)
    log.info("Done. %d card(s) collected.", len(cards))


if __name__ == "__main__":
    main()
