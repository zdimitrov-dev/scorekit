"""HTTP API for the frontend.

A thin FastAPI layer so the Next.js app can trigger the ingestion pipeline for a
piece it hasn't seen yet.

- ``GET /search`` — blocking: returns all of a piece's cards at once.
- ``GET /search/stream`` — streams cards **per source** as NDJSON so the UI can
  roll results out as they arrive (YouTube first, then IMSLP once enriched). Each
  batch is persisted before it's streamed, so cards carry real ids.

Run:  uvicorn scorekit.api:app --reload --port 8000
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .connectors import CONNECTORS
from .connectors.base import ConnectorUnavailable
from .db import get_client
from .jobs.ingest import ingest
from .matching import annotate_and_filter
from .models import Piece
from .normalize import normalize_slug
from .store import upsert_cards, upsert_piece

log = logging.getLogger("scorekit.api")

app = FastAPI(title="scorekit API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_CARD_SELECT = (
    "id,source,kind,external_id,url,title,thumbnail_url,author,metadata,"
    "piece:pieces(id,title,composer)"
)
_SEARCH_LIMIT = 25


def _cards_for_slug(slug: str) -> list[dict]:
    sb = get_client()
    piece = sb.table("pieces").select("id").eq("slug", slug).limit(1).execute().data
    if not piece:
        return []
    return (
        sb.table("cards").select(_CARD_SELECT).eq("piece_id", piece[0]["id"]).execute().data
        or []
    )


def _read_source(sb, piece_id: str, source: str) -> list[dict]:
    return (
        sb.table("cards").select(_CARD_SELECT)
        .eq("piece_id", piece_id).eq("source", source).execute().data
        or []
    )


def _ingest_stream(q: str, composer: str | None, limit: int, refresh: bool) -> Iterator[list[dict]]:
    """Yield one batch of persisted cards per source. Cached pieces replay their
    stored cards by source; new pieces run each connector, persist, then yield."""
    slug = normalize_slug(q, composer)
    sb = get_client()

    existing = sb.table("pieces").select("id").eq("slug", slug).limit(1).execute().data
    if existing and not refresh:
        pid = existing[0]["id"]
        for source in ("youtube", "imslp", "musescore"):
            batch = _read_source(sb, pid, source)
            if batch:
                yield batch
        return

    piece_id = upsert_piece(Piece(slug=slug, title=q, composer=composer))
    for connector_cls in CONNECTORS:
        connector = connector_cls()
        try:
            found = connector.search(q, limit=limit)
        except (NotImplementedError, ConnectorUnavailable) as exc:
            log.warning("[%s] skipped: %s", connector.source, exc)
            continue
        kept, _dropped = annotate_and_filter(found, q, composer)
        if connector.source == "imslp":
            kept = connector.enrich_cards(kept)
        if not kept:
            continue
        upsert_cards(piece_id, kept)
        batch = _read_source(sb, piece_id, connector.source)
        if batch:
            yield batch


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/search")
def search(
    q: str = Query(..., min_length=1),
    composer: str | None = None,
    refresh: bool = False,
) -> dict:
    slug = normalize_slug(q, composer)
    cards = _cards_for_slug(slug)
    if cards and not refresh:
        return {"slug": slug, "query": q, "ingested": False, "cards": cards}
    try:
        ingest(q, composer=composer, limit=_SEARCH_LIMIT, store=True)
    except Exception:
        log.exception("ingest failed for %r", q)
    return {"slug": slug, "query": q, "ingested": True, "cards": _cards_for_slug(slug)}


@app.get("/search/stream")
def search_stream(
    q: str = Query(..., min_length=1),
    composer: str | None = None,
    limit: int = _SEARCH_LIMIT,
    refresh: bool = False,
) -> StreamingResponse:
    def gen() -> Iterator[str]:
        try:
            for batch in _ingest_stream(q, composer, limit, refresh):
                yield json.dumps({"cards": batch}) + "\n"
        except Exception:
            log.exception("search stream failed for %r", q)
        yield json.dumps({"done": True}) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")
