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
from pydantic import BaseModel, Field

from .connectors import CONNECTORS
from .connectors.base import ConnectorUnavailable
from .db import get_client
from .jobs.ingest import ingest
from .matching import MATCHER_VERSION, annotate_and_filter
from .models import Piece
from .normalize import normalize_slug
from .piano import filter_piano
from .ml.registry import MIN_AUC_GAIN, MIN_POSITIVES, model_info
from .ml.serve import score_cards
from .recommend import SIGNAL_WEIGHTS, idf_weights, rank_cards
from .similar import similar_cards
from .store import log_events, retag_piece, upsert_cards, upsert_piece

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
_SOURCES = ("youtube", "imslp", "musescore")


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
    """Yield one batch of persisted cards per source.

    Cached sources replay their stored cards; sources with nothing cached are ingested
    live. The cache is keyed **per source, on actual cards** rather than on the
    existence of the piece row: a piece whose ingest stored nothing (a connector was
    down, out of quota, or its rows were later removed) would otherwise be a permanent
    negative cache — every repeat search replaying zero cards and reporting "no
    results" with no way to recover. This also lets a source that was unavailable on
    the first search fill itself in on a later one.
    """
    slug = normalize_slug(q, composer)
    sb = get_client()

    existing = sb.table("pieces").select("id").eq("slug", slug).limit(1).execute().data
    pending = list(_SOURCES)
    if existing and not refresh:
        pid = existing[0]["id"]
        for source in _SOURCES:
            batch = _read_source(sb, pid, source)
            # Cards scored by superseded matching are re-ingested rather than replayed:
            # the results the current scoring would keep were dropped before being
            # stored, so only a re-fetch can recover them (see matching.MATCHER_VERSION).
            if batch and all(
                (c.get("metadata") or {}).get("mv") == MATCHER_VERSION for c in batch
            ):
                pending.remove(source)
                yield batch
        if not pending:
            return

    piece_id = upsert_piece(Piece(slug=slug, title=q, composer=composer))
    for connector_cls in CONNECTORS:
        connector = connector_cls()
        if connector.source not in pending:
            continue
        try:
            found = connector.search(q, limit=limit)
        except (NotImplementedError, ConnectorUnavailable) as exc:
            log.warning("[%s] skipped: %s", connector.source, exc)
            continue
        # YouTube search is not a piano index: a query like "Rousseau" returns political
        # philosophy alongside that pianist's covers. IMSLP is already filtered by
        # instrument category and MuseScore returns sheet music by construction.
        if connector.source == "youtube":
            found, off_topic = filter_piano(found, q, composer)
            if off_topic:
                log.info("[youtube] dropped %d non-piano result(s) for %r", off_topic, q)
        kept, _dropped = annotate_and_filter(found, q, composer)
        if connector.source == "imslp":
            kept = connector.enrich_cards(kept)
        if not kept:
            continue
        upsert_cards(piece_id, kept)
        # Retag per source, not once at the end: this is a generator, so a client that
        # disconnects mid-stream would otherwise leave the piece ingested but untagged —
        # present in the corpus and invisible to the recommender.
        retag_piece(piece_id)
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


class Signal(BaseModel):
    """One engagement event. ``card_id`` is what the browser holds; the server resolves
    it to the piece, since taste is about pieces, not individual uploads."""

    card_id: str
    action: str = "like"


class RecommendRequest(BaseModel):
    signals: list[Signal] = Field(default_factory=list)
    limit: int = 60
    # Hold back the exact cards already engaged with — not their whole piece. Excluding
    # the piece meant liking a Liszt étude removed every Liszt card from the feed, which
    # reads as the recommender ignoring the like. Liking a piece should surface *more* of
    # it, and the diversity pass stops that becoming a wall of one piece.
    exclude_seen: bool = True
    # "auto" uses the learned model only once it has passed the gate; "model" forces it
    # even when it has not, for side-by-side testing; "content" pins the heuristic.
    ranker: str = "auto"


class InteractionEvent(BaseModel):
    """One logged signal. ``action`` is the feed's vocabulary (seen/like/save/click/skip);
    ``store.log_events`` maps it onto what the database can store."""

    action: str
    card_id: str | None = None
    piece_id: str | None = None
    dwell_ms: int | None = None
    feed_position: int | None = None


class InteractionBatch(BaseModel):
    # An anonymous per-browser id, generated client-side. No account, no PII — enough to
    # group one person's history for training, and replaceable by a real user id when auth
    # lands without touching the schema.
    user_id: str
    events: list[InteractionEvent] = Field(default_factory=list)


@app.post("/interactions")
def interactions(batch: InteractionBatch) -> dict:
    """Record feed signals — the recommender's training data (Phase 5).

    Batched because an impression is logged for every card seen, and never allowed to fail
    loudly: this is telemetry, so a broken write must cost some training data, never the
    user's action.
    """
    try:
        written = log_events([
            {**e.model_dump(), "user_id": batch.user_id} for e in batch.events
        ])
    except Exception:
        log.exception("failed to log %d interaction(s)", len(batch.events))
        return {"written": 0, "ok": False}
    return {"written": written, "ok": True}


_PAGE = 1000


def _all_cards(sb) -> list[dict]:
    """Every card, paged.

    A single capped query is the wrong shape here: PostgREST returns at most ~1000 rows,
    and the cap is silent — past that the feed would rank an arbitrary slice of the corpus
    and simply appear to get worse, with nothing to indicate why.
    """
    out: list[dict] = []
    while True:
        page = (
            sb.table("cards").select(_CARD_SELECT + ",piece_id")
            .range(len(out), len(out) + _PAGE - 1).execute().data
            or []
        )
        out.extend(page)
        if len(page) < _PAGE:
            return out


def _piece_tags(sb) -> dict[str, list[tuple[str, str]]]:
    """Every piece's tags, paged for the same reason as ``_all_cards``: a silently
    truncated tag table would drop pieces out of the feature space with no error."""
    tags: dict[str, list[tuple[str, str]]] = {}
    seen = 0
    while True:
        rows = (
            sb.table("piece_tags").select("piece_id,key,value")
            .range(seen, seen + _PAGE - 1).execute().data
            or []
        )
        for r in rows:
            tags.setdefault(r["piece_id"], []).append((r["key"], r["value"]))
        seen += len(rows)
        if len(rows) < _PAGE:
            return tags


@app.post("/recommend")
def recommend(req: RecommendRequest) -> dict:
    """Rank the whole corpus for one user's taste (content-based; see recommend.py).

    Takes signals in the request rather than reading a user row because likes/saves still
    live in the browser until auth lands (Phase 5). The ranker itself is indifferent to
    where they came from, so moving to the ``interactions`` table is a change here only.
    """
    sb = get_client()
    cards = _all_cards(sb)
    tags = _piece_tags(sb)

    # resolve the browser's card ids to piece ids
    by_card = {c["id"]: c.get("piece_id") for c in cards}
    signals: list[tuple[str, str]] = []
    seen_cards: set[str] = set()
    unknown = 0
    for s in req.signals:
        piece_id = by_card.get(s.card_id)
        if not piece_id:
            # a like on a card that no longer exists (e.g. the corpus was rebuilt)
            unknown += 1
            continue
        signals.append((piece_id, s.action))
        seen_cards.add(s.card_id)

    # The learned ranker supplies relevance when one has been promoted and the viewer has
    # a history for it to read; otherwise this is None and the content ranker is used. See
    # ml/registry for the gate a fit must pass before it is served.
    weights = idf_weights(tags)
    positives = [(piece_id, SIGNAL_WEIGHTS.get(action, 0.0))
                 for piece_id, action in signals if SIGNAL_WEIGHTS.get(action, 0.0) > 0]
    relevance = None
    if req.ranker != "content":
        relevance = score_cards(cards, tags, weights, positives,
                                force=req.ranker == "model")

    ranked = rank_cards(
        cards, tags, signals=signals, limit=req.limit,
        exclude_card_ids=seen_cards if req.exclude_seen else (),
        relevance=relevance,
    )
    return {
        "cards": ranked,
        "personalized": bool(signals),
        "tagged_pieces": len(tags),
        # surfaced so a feed that silently stopped personalising is diagnosable
        "unknown_signals": unknown,
        "ranker": "model" if relevance is not None else "content",
        "model": model_info(),
    }


@app.get("/dev/stats")
def dev_stats() -> dict:
    """Everything the dev dashboard shows: which ranker is live, what the model scored,
    and the shape of the corpus and the interaction log.

    A development surface, not part of the product. Remove it before release."""
    sb = get_client()

    def count(table: str) -> int:
        return sb.table(table).select("id", count="exact").limit(1).execute().count or 0

    actions: dict[str, int] = {}
    seen = 0
    while True:
        rows = (sb.table("interactions").select("action")
                .range(seen, seen + 999).execute().data or [])
        for r in rows:
            actions[r["action"]] = actions.get(r["action"], 0) + 1
        seen += len(rows)
        if len(rows) < 1000:
            break

    tags = _piece_tags(sb)
    sources: dict[str, int] = {}
    for c in _all_cards(sb):
        sources[c["source"]] = sources.get(c["source"], 0) + 1

    info = model_info()
    return {
        "model": info,
        "active_ranker": "model" if info.get("promoted") else "content",
        "corpus": {
            "pieces": count("pieces"),
            "cards": sum(sources.values()),
            "cards_by_source": sources,
            "tagged_pieces": len(tags),
            "distinct_tags": len({t for v in tags.values() for t in v}),
        },
        "interactions": {
            "total": sum(actions.values()),
            "by_action": actions,
            "positives": actions.get("like", 0) + actions.get("save", 0),
        },
        "gate": {"min_positives": MIN_POSITIVES, "min_auc_gain": MIN_AUC_GAIN},
    }


@app.get("/similar")
def similar(card_id: str, limit: int = 12) -> dict:
    """Cards like one specific card — what the modal shows underneath it.

    Ranked against the opened card alone, never against the viewer's taste, so it works
    the first time someone clicks in and cannot pull the home feed around.
    """
    sb = get_client()
    cards = _all_cards(sb)
    anchor = next((c for c in cards if c["id"] == card_id), None)
    if anchor is None:
        return {"cards": [], "anchor": None}
    tags = _piece_tags(sb)
    return {
        "anchor": card_id,
        "cards": similar_cards(anchor, cards, tags, idf_weights(tags), limit),
    }


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
