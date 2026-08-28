"""MuseScore connector — Phase 3.

MuseScore's public API was discontinued and hitting the site directly gets IPs
blocked, so we **never touch MuseScore's servers**. Instead we query Google's index
restricted to ``musescore.com`` via the Google Custom Search JSON API, and link out
to the listings Google already indexed. Each result becomes a ``kind="listing"``
card (with a preview thumbnail, unlike IMSLP).

Gated by config: ``search()`` raises ``ConnectorUnavailable`` until both
``GOOGLE_CSE_ID`` and ``GOOGLE_CSE_KEY`` are set, so the ingest job skips it until
you've created a Programmable Search Engine (restricted to musescore.com) and an
API key.

**Quota is the defining constraint** — the Custom Search JSON API allows only 100
queries/day free (then paid, hard-capped at 10k/day). So responses are **cached
per query** (a small TTL file cache by default) to avoid re-spending quota on the
same piece, and an HTTP 429 is treated as ``ConnectorUnavailable`` (skip, don't
crash the run).

Caveat: MuseScore listings are discovery links; many downloads require a MuseScore
Pro subscription — these are not guaranteed-free scores like IMSLP's public domain.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from .base import Connector, ConnectorUnavailable
from ..config import settings
from ..models import Card

CSE_API = "https://www.googleapis.com/customsearch/v1"
USER_AGENT = "scorekit/0.0 (+https://github.com/zdimitrov-dev/scorekit)"
# CSE returns at most 10 results per request; more needs paginated `start` (extra quota).
MAX_RESULTS = 10
CACHE_TTL_DAYS = 30
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "scorekit" / "musescore"

_SCORE_ID_RE = re.compile(r"/scores/(\d+)")
# Trailing "| Musescore.com" site branding on result titles.
_SITE_SUFFIX_RE = re.compile(r"\s*\|\s*musescore\.com\s*$", re.IGNORECASE)


def _score_id(url: str) -> str:
    """Stable external_id for a MuseScore result: the numeric score id if present,
    else the URL without query/fragment (still unique)."""
    m = _SCORE_ID_RE.search(url)
    if m:
        return m.group(1)
    return url.split("?", 1)[0].split("#", 1)[0]


def _clean_title(title: str) -> str:
    """Drop the trailing '| Musescore.com' site branding from a result title."""
    return _SITE_SUFFIX_RE.sub("", title or "").strip()


def _thumbnail(pagemap: dict) -> str | None:
    """Best preview image from a CSE result's pagemap."""
    thumbs = pagemap.get("cse_thumbnail") or []
    if thumbs and thumbs[0].get("src"):
        return thumbs[0]["src"]
    metatags = pagemap.get("metatags") or []
    if metatags and metatags[0].get("og:image"):
        return metatags[0]["og:image"]
    images = pagemap.get("cse_image") or []
    if images and images[0].get("src"):
        return images[0]["src"]
    return None


class _FileCache:
    """Tiny TTL file cache for raw CSE responses so we don't re-spend Google
    Custom Search quota on the same query. Best-effort: any IO error is ignored."""

    def __init__(self, directory: Path = DEFAULT_CACHE_DIR, ttl_days: int = CACHE_TTL_DAYS) -> None:
        self.dir = Path(directory)
        self.ttl = timedelta(days=ttl_days)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        return self.dir / f"{digest}.json"

    def get(self, key: str) -> dict | None:
        path = self._path(key)
        try:
            if not path.exists():
                return None
            age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
            if age > self.ttl:
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def set(self, key: str, value: dict) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._path(key).write_text(json.dumps(value), encoding="utf-8")
        except Exception:
            pass


class MuseScoreConnector(Connector):
    source = "musescore"

    def __init__(self, client: Any = None, cache: Any = None) -> None:
        # httpx-like client and a get/set cache can be injected (tests); both are
        # built lazily otherwise.
        self._client = client
        self._cache = cache

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15.0)
        return self._client

    @property
    def cache(self) -> Any:
        if self._cache is None:
            self._cache = _FileCache()
        return self._cache

    def search(self, query: str, limit: int = 20) -> list[Card]:
        if not (settings.google_cse_id and settings.google_cse_key):
            raise ConnectorUnavailable(
                "GOOGLE_CSE_ID and GOOGLE_CSE_KEY must be set for the MuseScore "
                "connector (see .env.example)."
            )
        num = max(1, min(limit, MAX_RESULTS))
        key = f"musescore:{query.strip().lower()}:{num}"
        data = self.cache.get(key)
        if data is None:
            data = self._fetch(query, num)
            self.cache.set(key, data)

        return [self._to_card(item) for item in data.get("items", [])]

    def _fetch(self, query: str, num: int) -> dict:
        resp = self.client.get(CSE_API, params={
            "key": settings.google_cse_key,
            "cx": settings.google_cse_id,
            "q": query,
            "siteSearch": "musescore.com",   # force the site even if the CSE isn't restricted
            "siteSearchFilter": "i",
            "num": num,
        })
        if getattr(resp, "status_code", 200) == 429:
            raise ConnectorUnavailable("Google Custom Search quota exceeded (HTTP 429).")
        resp.raise_for_status()
        return resp.json()

    def _to_card(self, item: dict) -> Card:
        url = item.get("link", "")
        pagemap = item.get("pagemap", {}) or {}
        return Card(
            source=self.source,
            external_id=_score_id(url),
            url=url,
            title=_clean_title(item.get("title", "")) or None,
            kind="listing",
            thumbnail_url=_thumbnail(pagemap),
            author=None,                     # uploader not reliably in the CSE result; TODO
            metadata={
                "snippet": item.get("snippet"),
                "display_link": item.get("displayLink"),
                # TODO(verify-live): parse instrumentation / arranger from title/pagemap.
            },
        )
