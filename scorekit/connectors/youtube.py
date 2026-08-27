"""YouTube connector — Phase 1.

Searches the official YouTube Data API (v3) and normalizes each result into a
``Card``. Video descriptions often already contain sheet-music links (MuseScore,
IMSLP, ...), so we capture those in ``Card.metadata`` as bonus signal for later.
"""
from __future__ import annotations

import html
import re
from typing import Any

from googleapiclient.discovery import build

from .base import Connector, ConnectorUnavailable
from ..config import settings
from ..models import Card

# Substrings in a URL that suggest it points at sheet music.
_SHEET_HINTS = (
    "musescore.com", "imslp.org", "sheetmusicplus", "mymusicsheet",
    "gumroad.com", "sheet",
)
_URL_RE = re.compile(r"https?://[^\s)>\]]+")


def _classify_kind(title: str) -> str | None:
    """Best-effort map of a video title to a ``card_kind``. ``None`` when unsure."""
    t = title.lower()
    if any(k in t for k in ("tutorial", "how to play", "lesson", "easy piano", "synthesia")):
        return "tutorial"
    if "cover" in t:
        return "cover"
    if any(k in t for k in ("performance", "live", "concert", "recital", "plays")):
        return "performance"
    return None


def _extract_sheet_links(description: str) -> list[str]:
    """Return the (de-duplicated) URLs in a description that look like sheet music."""
    out: list[str] = []
    for url in _URL_RE.findall(description or ""):
        url = url.rstrip(".,);")
        if any(hint in url.lower() for hint in _SHEET_HINTS) and url not in out:
            out.append(url)
    return out


class YouTubeConnector(Connector):
    source = "youtube"

    def __init__(self, client: Any = None) -> None:
        # A prebuilt API client can be injected (used in tests); otherwise it is
        # built lazily from the configured API key on first use.
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            if not settings.youtube_api_key:
                raise ConnectorUnavailable("YOUTUBE_API_KEY is not set (see .env.example).")
            self._client = build(
                "youtube", "v3",
                developerKey=settings.youtube_api_key,
                cache_discovery=False,
            )
        return self._client

    def search(self, query: str, limit: int = 20) -> list[Card]:
        response = (
            self.client.search()
            .list(q=query, part="snippet", type="video", maxResults=max(1, min(limit, 50)))
            .execute()
        )
        return [
            self._to_card(item)
            for item in response.get("items", [])
            if item.get("id", {}).get("videoId")
        ]

    def _to_card(self, item: dict) -> Card:
        video_id = item["id"]["videoId"]
        snippet = item.get("snippet", {})
        title = html.unescape(snippet.get("title", "")) or None
        description = snippet.get("description", "") or ""
        thumbs = snippet.get("thumbnails", {})
        thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
        links = _extract_sheet_links(description)
        return Card(
            source=self.source,
            external_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            title=title,
            kind=_classify_kind(title or ""),
            thumbnail_url=thumb,
            author=html.unescape(snippet.get("channelTitle", "")) or None,
            metadata={
                "channel_id": snippet.get("channelId"),
                "published_at": snippet.get("publishedAt"),
                "description_excerpt": description[:500],
                "has_sheet_music_link": bool(links),
                "sheet_music_links": links,
            },
        )
