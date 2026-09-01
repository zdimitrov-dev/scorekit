"""Remove stored YouTube cards that the current piano filter would reject.

Ingestion only ever adds and updates. A card stored before a filter existed, or before it
was improved, stays in the corpus forever: the "Rousseau" search still served
political-philosophy lectures long after the filter that rejects them was written, because
re-ingesting the piece added the good cards without removing the bad ones.

Deliberately narrow. It re-runs `piano.is_piano` over what is already stored and deletes
only what fails, rather than deleting anything absent from a fresh search result. A flaky
API response that returns three results must never be able to wipe twenty good cards.

    python -m scorekit.jobs.purge --dry-run
    python -m scorekit.jobs.purge
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from ..db import get_client
from ..models import Card
from ..piano import filter_piano

log = logging.getLogger("scorekit.purge")


def _page(sb, table: str, select: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while True:
        rows = sb.table(table).select(select).range(len(out), len(out) + 999).execute().data or []
        out += rows
        if len(rows) < 1000:
            return out


def _as_card(row: dict[str, Any]) -> Card:
    return Card(
        source=row["source"],
        external_id=row.get("external_id") or row["id"],
        url=row.get("url") or "",
        title=row.get("title"),
        author=row.get("author"),
        metadata=row.get("metadata") or {},
    )


def purge(dry_run: bool = False) -> tuple[int, int]:
    """Returns (checked, removed)."""
    sb = get_client()
    pieces = {p["id"]: p for p in _page(sb, "pieces", "id,slug,title,composer")}
    cards = [c for c in _page(sb, "cards", "id,piece_id,source,external_id,url,title,author,metadata")
             if c["source"] == "youtube"]

    # Grouped by piece, and filtered as a set rather than card by card. The filter lets a
    # channel that has proved itself vouch for its other uploads, and judging each card
    # alone loses that: it wanted to delete Rousseau's Vivaldi, Einaudi and Rachmaninoff
    # performances, none of which say "piano" on their own.
    by_piece: dict[str, list[dict[str, Any]]] = {}
    for row in cards:
        by_piece.setdefault(row["piece_id"], []).append(row)

    doomed: list[dict[str, Any]] = []
    for piece_id, rows in by_piece.items():
        piece = pieces.get(piece_id, {})
        # The piece's own title stands in for the query it was ingested under, which is
        # what the filter's repertoire fallback needs.
        kept, _ = filter_piano([_as_card(r) for r in rows],
                               piece.get("title") or "", piece.get("composer"))
        survivors = {c.external_id for c in kept}
        doomed += [r for r in rows if (r.get("external_id") or r["id"]) not in survivors]

    for row in doomed:
        slug = pieces.get(row["piece_id"], {}).get("slug", "?")
        log.info("  remove  %-28s %s", slug[:28], (row.get("title") or "")[:52])
        if not dry_run:
            sb.table("cards").delete().eq("id", row["id"]).execute()
    return len(cards), len(doomed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete stored non-piano YouTube cards.")
    parser.add_argument("--dry-run", action="store_true", help="list them, delete nothing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    checked, removed = purge(dry_run=args.dry_run)
    log.info("\n%schecked %d youtube cards, %d fail the piano filter",
             "[dry-run] " if args.dry_run else "", checked, removed)


if __name__ == "__main__":
    main()
