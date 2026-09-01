"""Persistence helpers — upsert normalized pieces and cards into Supabase.

Kept separate from the connectors (which only *produce* Cards) and from the
ingest orchestrator (which decides *when* to persist), so the write path is easy
to test in isolation with an injected client.
"""
from __future__ import annotations

import logging
from typing import Any

from .db import get_client
from .models import Card, Piece
from .tagging import derive_tags, tag_rows

log = logging.getLogger("scorekit.store")


def upsert_piece(piece: Piece, client: Any = None) -> str:
    """Insert or update a piece by its unique ``slug``; return its ``id``.

    ``None`` fields are dropped so an update never overwrites an existing value
    (e.g. a known ``composer``) with null.
    """
    client = client or get_client()
    payload = {
        "slug": piece.slug,
        "title": piece.title,
        "composer": piece.composer,
        "era": piece.era,
        "genre": piece.genre,
        "difficulty": piece.difficulty,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    result = client.table("pieces").upsert(payload, on_conflict="slug").execute()
    return result.data[0]["id"]


def upsert_cards(piece_id: str, cards: list[Card], client: Any = None) -> int:
    """Insert or update cards for a piece, de-duplicated on ``(source, external_id)``.

    Returns the number of card rows written.
    """
    if not cards:
        return 0
    client = client or get_client()
    rows = [
        {
            "piece_id": piece_id,
            "source": c.source,
            "kind": c.kind,
            "external_id": c.external_id,
            "url": c.url,
            "title": c.title,
            "thumbnail_url": c.thumbnail_url,
            "author": c.author,
            "metadata": c.metadata or {},
        }
        for c in cards
    ]
    result = client.table("cards").upsert(rows, on_conflict="source,external_id").execute()
    return len(result.data)


# What the feed reports -> what the `interaction_action` enum stores.
#
# `seen` is a card that was scrolled into view and not engaged with — the implicit negative
# the recommender trains against. It is deliberately *not* `skip`: once an explicit reject
# control exists, "passed over" and "rejected" carry different confidence and must be
# weighted differently, and collapsing them at write time would be unrecoverable.
_ACTION_MAP = {
    "seen": "impression",
    "skip": "skip",
    "like": "like",
    "save": "save",
    "click": "click",
}


_backfilled_column: bool | None = None


def has_backfilled_column(client: Any = None) -> bool:
    """Whether migration 002 has been applied.

    Checked rather than assumed because the migration runner cannot reach the legacy
    database host, so the column is usually applied by hand and may lag the code. Writing
    a column that does not exist would fail the whole insert.
    """
    global _backfilled_column
    if _backfilled_column is None:
        try:
            (client or get_client()).table("interactions").select("backfilled").limit(1).execute()
            _backfilled_column = True
        except Exception:
            log.info("interactions.backfilled is missing; apply db/migrations/002")
            _backfilled_column = False
    return _backfilled_column


def log_events(events: list[dict[str, Any]], client: Any = None) -> int:
    """Append interaction events. Returns the number of rows written.

    Append-only and best-effort by design: this is the recommender's training signal, not
    application state, so a lost event costs a little data and must never cost the user an
    action. Unknown action names are dropped rather than raising.
    """
    rows = []
    for e in events:
        action = _ACTION_MAP.get(str(e.get("action", "")).lower())
        if not action or not e.get("user_id"):
            continue
        dwell = e.get("dwell_ms")
        position = e.get("feed_position")
        row = {
            "user_id": e["user_id"],
            "card_id": e.get("card_id"),
            "piece_id": e.get("piece_id"),
            "action": action,
            "dwell_ms": max(0, int(dwell)) if isinstance(dwell, (int, float)) else None,
            "feed_position": int(position) if isinstance(position, (int, float)) else None,
        }
        # created_at is the sync time for a reconciled row, so it carries no ordering
        # information and training must not read it as chronology. See migration 002.
        if e.get("backfilled") and has_backfilled_column(client):
            row["backfilled"] = True
        rows.append(row)
    if not rows:
        return 0
    client = client or get_client()
    result = client.table("interactions").insert(rows).execute()
    return len(result.data or [])


def retag_piece(piece_id: str, client: Any = None) -> int:
    """Re-derive and replace this piece's ``piece_tags`` from its stored cards.

    Called after every ingest, because tags are what the recommender ranks on: a piece
    that is ingested but never tagged has zero affinity and is invisible to the home
    feed no matter how many times the user likes it. Leaving tagging to the batch job
    meant every piece searched since the last run was silently unrecommendable.

    Replaces rather than merges, so re-running after a vocabulary change strands nothing.
    """
    client = client or get_client()
    piece = (
        client.table("pieces").select("id,title,composer").eq("id", piece_id)
        .limit(1).execute().data
    )
    if not piece:
        return 0
    cards = (
        client.table("cards").select("source,kind,title,author,metadata")
        .eq("piece_id", piece_id).execute().data
        or []
    )
    rows = tag_rows(piece_id, derive_tags(piece[0], cards))
    client.table("piece_tags").delete().eq("piece_id", piece_id).execute()
    if rows:
        client.table("piece_tags").insert(rows).execute()
    return len(rows)
