"""Tagging job — (re)build ``piece_tags`` for every piece from its cards.

Feature extraction is deliberately a **batch job over stored data** rather than
something the ingest pipeline does inline: the tag vocabulary in ``scorekit.tagging``
will keep changing as the recommender develops, and re-deriving the whole corpus has to
stay a one-command operation. It is idempotent — tags are replaced per piece, so a run
after a vocabulary change leaves no stale rows behind.

It also backfills ``pieces.composer`` when the piece was created from a query that never
named one ("Op 48 No 1"), using the composer its IMSLP cards agree on.

    python -m scorekit.jobs.tag_pieces
    python -m scorekit.jobs.tag_pieces --dry-run
    python -m scorekit.jobs.tag_pieces --slug debussy-clair-de-lune
"""
from __future__ import annotations

import argparse
import logging
from collections import Counter

from ..db import get_client
from ..tagging import _infer_composer, derive_tags, tag_rows

log = logging.getLogger("scorekit.tag_pieces")

_CARD_FIELDS = "id,source,kind,title,author,metadata"


def _backfill_composer(sb, piece: dict, cards: list[dict], dry_run: bool) -> str | None:
    """Set ``pieces.composer`` when the piece was created from a query that never named
    one. Delegates to the same voted inference the tags use, so the stored composer and
    the ``composer`` tag can never disagree."""
    if piece.get("composer"):
        return piece["composer"]
    composer = _infer_composer(piece, cards)
    if not composer:
        return None
    if not dry_run:
        sb.table("pieces").update({"composer": composer}).eq("id", piece["id"]).execute()
    log.info("  composer backfilled -> %s", composer)
    return composer


def tag_pieces(slug: str | None = None, dry_run: bool = False) -> dict[str, int]:
    sb = get_client()
    query = sb.table("pieces").select("id,slug,title,composer")
    if slug:
        query = query.eq("slug", slug)
    pieces = query.execute().data or []

    totals = Counter()
    for piece in pieces:
        cards = (
            sb.table("cards").select(_CARD_FIELDS).eq("piece_id", piece["id"]).execute().data
            or []
        )
        piece["composer"] = _backfill_composer(sb, piece, cards, dry_run)

        tags = derive_tags(piece, cards)
        rows = tag_rows(piece["id"], tags)
        log.info(
            "%-32s %2d cards -> %2d tags  %s",
            piece["slug"], len(cards), len(rows),
            ", ".join(f"{k}={v}" for k, v in sorted(tags)) or "(none)",
        )
        if not dry_run:
            # replace rather than upsert: a vocabulary change must not strand old rows
            sb.table("piece_tags").delete().eq("piece_id", piece["id"]).execute()
            if rows:
                sb.table("piece_tags").insert(rows).execute()

        totals["pieces"] += 1
        totals["tags"] += len(rows)
        if not rows:
            totals["untagged"] += 1
    return dict(totals)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild piece_tags from stored cards.")
    parser.add_argument("--slug", help="only tag this piece")
    parser.add_argument("--dry-run", action="store_true", help="print tags, write nothing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    totals = tag_pieces(slug=args.slug, dry_run=args.dry_run)
    log.info(
        "\n%s%d pieces, %d tags (%d pieces untagged)",
        "[dry-run] " if args.dry_run else "",
        totals.get("pieces", 0), totals.get("tags", 0), totals.get("untagged", 0),
    )


if __name__ == "__main__":
    main()
