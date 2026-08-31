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
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from .base import Connector, ConnectorUnavailable
from ..config import settings
from ..models import Card

TAVILY_API = "https://api.tavily.com/search"
TAVILY_EXTRACT_API = "https://api.tavily.com/extract"
USER_AGENT = "scorekit/0.0 (+https://github.com/zdimitrov-dev/scorekit)"
MAX_RESULTS = 20   # Tavily's per-request maximum
CACHE_TTL_DAYS = 30
# Part of the cache key: bump when what we *derive* from a response changes, so improved
# extraction is not masked for 30 days by entries built with the older logic. Adding the
# raw_content and extract passes lifted thumbnail coverage from ~20% to ~90%, and every
# already-cached query kept serving the old 20% until this existed.
CACHE_VERSION = 2
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "scorekit" / "musescore"

log = logging.getLogger("scorekit.musescore")

_SCORE_ID_RE = re.compile(r"/scores/(\d+)")
# Trailing "| Musescore.com" site branding on result titles.
_SITE_SUFFIX_RE = re.compile(r"\s*\|\s*musescore\.com\s*$", re.IGNORECASE)

# The engraved first page of a score, as referenced on a MuseScore listing page.
_SCOREDATA_RE = re.compile(r"/scoredata/g/([0-9a-f]{40})/score_0\b")
# MuseScore's image CDN, which serves the same asset with an "@WxH" resize suffix.
# We must go through it: musescore.com/static/... answers hotlinked requests with 403,
# so the URL that appears on the page is useless as a thumbnail for our feed.
_CDN = "https://cdn.ustatik.com/musescore/scoredata/g/{h}/score_0.png@{w}x{ht}?bgclr=ffffff"
# Portrait, matching a sheet-music page and the scale of our other sources' thumbnails.
THUMB_WIDTH, THUMB_HEIGHT = 600, 840


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
    """Build a first-page score thumbnail from a Tavily result, or ``None``.

    A result's ``images`` are simply everything scraped off the listing page — mostly
    chrome: the green/blue "Pro" sale banner, app-store badges, ad-network tracking
    pixels. Only one entry is the score itself, identified by its ``/scoredata/g/<hash>/
    score_0`` path, and we rebuild that hash into a correctly sized CDN URL rather than
    using the on-page link (see ``_CDN``).

    ``images`` alone finds the engraving on roughly a third of results, so we fall back to
    scanning ``raw_content`` (the page HTML Tavily already fetched), which about doubles
    coverage. Closing the remaining gap would mean requesting MuseScore's pages ourselves,
    which this connector deliberately never does — see the module docstring.

    Returning ``None`` is a normal outcome, and the feed renders its own titled tile for
    those, which beats showing a promo banner.
    """
    urls: list[str] = []
    for im in result.get("images") or []:
        if isinstance(im, str):
            urls.append(im)
        elif isinstance(im, dict) and im.get("url"):
            urls.append(im["url"])

    for url in urls:
        m = _SCOREDATA_RE.search(url)
        if m:
            return _CDN.format(h=m.group(1), w=THUMB_WIDTH, ht=THUMB_HEIGHT)

    m = _SCOREDATA_RE.search(result.get("raw_content") or "")
    if m:
        return _CDN.format(h=m.group(1), w=THUMB_WIDTH, ht=THUMB_HEIGHT)
    return None


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
        key = f"musescore:v{CACHE_VERSION}:{query.strip().lower()}:{num}"
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
                # page HTML, used only to find the score engraving `images` missed
                "include_raw_content": True,
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
        data = resp.json()

        # Resolve thumbnails now and drop raw_content before this is cached: it is only
        # needed for that one regex, and storing whole pages for 20 results would bloat
        # the query cache by megabytes per search.
        results = data.get("results", [])
        for result in results:
            result["thumbnail"] = _thumbnail(result)
            result.pop("raw_content", None)
        self._fill_missing_thumbnails(results)
        return data

    def _fill_missing_thumbnails(self, results: list[dict]) -> None:
        """Second pass for listings whose search result carried no engraving.

        MuseScore answers direct requests with 403 (bot protection), so we cannot fetch
        the page ourselves — and would not want to, per the module docstring. Tavily's
        ``/extract`` fetches through their own infrastructure instead; ``advanced`` depth
        renders the page, which is what surfaces the score image on the stragglers. One
        batched call per search, and purely additive: any failure leaves the tile
        fallback in place rather than breaking the ingest.
        """
        missing = [r for r in results if not r.get("thumbnail") and r.get("url")]
        if not missing:
            return
        try:
            resp = self.client.post(
                TAVILY_EXTRACT_API,
                headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
                json={
                    "urls": [r["url"] for r in missing],
                    "extract_depth": "advanced",
                    "include_images": True,
                },
            )
            if getattr(resp, "status_code", 200) != 200:
                return
            extracted = {r.get("url"): r for r in resp.json().get("results", [])}
        except Exception:
            log.debug("thumbnail extract pass failed; falling back to themed tiles")
            return

        for result in missing:
            page = extracted.get(result["url"])
            if page:
                result["thumbnail"] = _thumbnail(page)

    def _to_card(self, result: dict) -> Card:
        url = result.get("url", "")
        return Card(
            source=self.source,
            external_id=_score_id(url),
            url=url,
            title=_clean_title(result.get("title", "")) or None,
            kind="listing",
            # resolved at fetch time; recomputed for entries cached before that change
            thumbnail_url=result.get("thumbnail") or _thumbnail(result),
            author=None,                     # uploader not in the result; TODO(verify-live)
            metadata={
                "snippet": result.get("content"),
                "tavily_score": result.get("score"),
            },
        )
