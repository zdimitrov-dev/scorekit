"""Ingestion job — runs every connector for a query and (later) upserts results.

Phase 0: wires the connector registry and the CLI. Connectors raise
NotImplementedError until their phase lands, so a run currently reports which
sources are pending rather than writing anything.

    python -m scorekit.jobs.ingest --query "Clair de Lune"
"""
from __future__ import annotations

import argparse
import logging

from ..connectors import CONNECTORS
from ..models import Card
from ..normalize import normalize_slug

log = logging.getLogger("scorekit.ingest")


def ingest(query: str, composer: str | None = None, limit: int = 20) -> list[Card]:
    slug = normalize_slug(query, composer)
    log.info("Ingesting query=%r composer=%r -> slug=%r", query, composer, slug)

    cards: list[Card] = []
    for connector_cls in CONNECTORS:
        connector = connector_cls()
        try:
            found = connector.search(query, limit=limit)
        except NotImplementedError as exc:
            log.warning("[%s] skipped: %s", connector.source, exc)
            continue
        log.info("[%s] returned %d card(s)", connector.source, len(found))
        cards.extend(found)

    # TODO(Phase 1+): upsert piece (slug) and cards into Supabase via scorekit.db.
    return cards


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a scorekit ingestion.")
    parser.add_argument("--query", required=True, help="Piece to search for.")
    parser.add_argument("--composer", default=None, help="Optional composer hint.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(levelname)s %(name)s: %(message)s",
    )
    cards = ingest(args.query, composer=args.composer, limit=args.limit)
    log.info("Done. %d card(s) collected.", len(cards))


if __name__ == "__main__":
    main()
