"""MuseScore connector — Phase 3.

MuseScore's public API was discontinued and hitting the site directly gets IPs
blocked, so we **never touch MuseScore's servers**. Instead we query the **Tavily
search API** restricted to ``musescore.com`` (``include_domains``) and link out to
the listings it indexed. Each result becomes a ``kind="listing"`` card.

(The original plan used Google's Custom Search JSON API, but Google closed that API
to new projects — hence the switch to Tavily.)

Gated by config: ``search()`` raises ``ConnectorUnavailable`` until ``TAVILY_API_KEY``
is set, so the ingest job skips it until you've added a key (tavily.com — free tier
is ~1,000 searches/month). Responses are **cached per query** (a TTL file cache) to
stay within that budget, and auth/quota errors (401/403/429) are treated as
``ConnectorUnavailable`` (skip, don't crash the run).

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

TAVILY_API = "https://api.tavily.com/search"
USER_AGENT = "scorekit/0.0 (+https://github.com/zdimitrov-dev/scorekit)"
MAX_RESULTS = 20   # Tavily's per-request maximum
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


def _thumbnail(result: dict) -> str | None:
    """Best score-preview image from a Tavily result, skipping MuseScore's promo /
    sale banners (the green/blue "Pro" ads that otherwise render as a weird strip)."""
    urls: list[str] = []
    for im in result.get("images") or []:
        if isinstance(im, str):
            urls.append(im)
        elif isinstance(im, dict) and im.get("url"):
            urls.append(im["url"])
    # prefer an actual first-page score render
    score = [u for u in urls if "scoredata" in u or "/score_" in u]
    if score:
        return score[0]
    non_promo = [u for u in urls if "sale_offer" not in u and "image_desktop" not in u]
    return non_promo[0] if non_promo else None


class _FileCache:
    """Tiny TTL file cache for raw search responses so we don't re-spend the Tavily
    query budget on the same piece. Best-effort: any IO error is ignored."""

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
            self._client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20.0)
        return self._client

    @property
    def cache(self) -> Any:
        if self._cache is None:
            self._cache = _FileCache()
        return self._cache

    def search(self, query: str, limit: int = 20) -> list[Card]:
        if not settings.tavily_api_key:
            raise ConnectorUnavailable(
                "TAVILY_API_KEY must be set for the MuseScore connector (see .env.example)."
            )
        num = max(1, min(limit, MAX_RESULTS))
        key = f"musescore:{query.strip().lower()}:{num}"
        data = self.cache.get(key)
        if data is None:
            data = self._fetch(query, num)
            self.cache.set(key, data)

        return [self._to_card(r) for r in data.get("results", [])]

    def _fetch(self, query: str, num: int) -> dict:
        resp = self.client.post(
            TAVILY_API,
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            json={
                "query": query,
                "include_domains": ["musescore.com"],
                "max_results": num,
                "search_depth": "basic",
                "include_images": True,
            },
        )
        status = getattr(resp, "status_code", 200)
        if status in (401, 403):
            raise ConnectorUnavailable(
                f"Tavily access denied (HTTP {status}) — check TAVILY_API_KEY."
            )
        if status == 429:
            raise ConnectorUnavailable("Tavily rate limit / quota exceeded (HTTP 429).")
        resp.raise_for_status()
        return resp.json()

    def _to_card(self, result: dict) -> Card:
        url = result.get("url", "")
        return Card(
            source=self.source,
            external_id=_score_id(url),
            url=url,
            title=_clean_title(result.get("title", "")) or None,
            kind="listing",
            thumbnail_url=_thumbnail(result),
            author=None,                     # uploader not in the result; TODO(verify-live)
            metadata={
                "snippet": result.get("content"),
                "tavily_score": result.get("score"),
            },
        )
