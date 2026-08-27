"""YouTube connector — Phase 1.

Two-step pipeline against the official YouTube Data API (v3):

1. ``search.list`` finds candidate videos for the query (relevance order).
2. ``videos.list`` fetches full details for those ids — crucially the *full*
   description (search only returns a truncated snippet), plus duration and
   view count.

Each result is normalized into a ``Card``. Duration lets us flag long
"compilation" videos (mixes / hours-long loops) so the feed can offer an
"individual pieces only" view. YouTube's auto-generated ``... - Topic`` channels
are skipped — they are duplicate official-audio uploads, usually lower-view
copies of the real source. Sheet-music links found in the full description are
captured in ``Card.metadata`` as bonus signal.
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

# Whole-word title cues that mark a compilation regardless of length. Word
# boundaries matter so "mix" does not match inside "remix".
_COMPILATION_RE = re.compile(
    r"\b(?:compilation|mix|playlist|best of|collection|hours|full album)\b"
)
# A video at/over this length is treated as a compilation. Tunable — the raw
# duration is stored in metadata so the threshold can change without re-ingesting.
COMPILATION_MIN_SECONDS = 15 * 60

# ISO-8601 duration, e.g. "PT8M30S" or "P1DT2H3M4S".
_DURATION_RE = re.compile(r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _parse_duration(iso: str | None) -> int | None:
    """Convert an ISO-8601 duration (e.g. ``'PT8M30S'``) to whole seconds."""
    if not iso:
        return None
    m = _DURATION_RE.fullmatch(iso)
    if not m:
        return None
    days, hours, minutes, seconds = (int(x) if x else 0 for x in m.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _is_topic_channel(author: str | None) -> bool:
    """True for YouTube's auto-generated ``... - Topic`` channels — duplicate
    official-audio uploads we skip in favor of the real source."""
    return bool(author) and author.strip().lower().endswith("- topic")


def _classify_kind(title: str) -> str | None:
    """Best-effort map of a video to a ``card_kind`` (format). ``None`` if unsure."""
    t = title.lower()
    if any(k in t for k in ("tutorial", "how to play", "lesson", "easy piano", "synthesia")):
        return "tutorial"
    if "cover" in t:
        return "cover"
    if any(k in t for k in ("performance", "live", "concert", "recital", "plays")):
        return "performance"
    return None


def _is_compilation(title: str, duration_seconds: int | None) -> bool:
    """A long video, or one whose title screams mix / hours / compilation."""
    if duration_seconds is not None and duration_seconds >= COMPILATION_MIN_SECONDS:
        return True
    return bool(_COMPILATION_RE.search(title.lower()))


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
        # 1) relevance-ordered candidate video ids
        search_resp = (
            self.client.search()
            .list(q=query, part="snippet", type="video", maxResults=max(1, min(limit, 50)))
            .execute()
        )
        ids = [
            item["id"]["videoId"]
            for item in search_resp.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not ids:
            return []

        # 2) full details (full description, duration, view count) for those ids
        details_resp = (
            self.client.videos()
            .list(part="snippet,contentDetails,statistics", id=",".join(ids))
            .execute()
        )
        details = {v["id"]: v for v in details_resp.get("items", [])}

        # rebuild in relevance order, dropping auto-generated "- Topic" channels
        cards: list[Card] = []
        for vid in ids:
            video = details.get(vid)
            if video is None:
                continue
            if _is_topic_channel(video.get("snippet", {}).get("channelTitle", "")):
                continue
            cards.append(self._to_card(video))
        return cards

    def _to_card(self, video: dict) -> Card:
        video_id = video["id"]
        snippet = video.get("snippet", {})
        content = video.get("contentDetails", {})
        stats = video.get("statistics", {})

        title = html.unescape(snippet.get("title", "")) or None
        description = snippet.get("description", "") or ""
        author = html.unescape(snippet.get("channelTitle", "")) or None
        thumbs = snippet.get("thumbnails", {})
        thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")

        duration_seconds = _parse_duration(content.get("duration"))
        view_count = int(stats["viewCount"]) if stats.get("viewCount", "").isdigit() else None
        links = _extract_sheet_links(description)

        return Card(
            source=self.source,
            external_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            title=title,
            kind=_classify_kind(title or ""),
            thumbnail_url=thumb,
            author=author,
            metadata={
                "channel_id": snippet.get("channelId"),
                "published_at": snippet.get("publishedAt"),
                "duration_iso": content.get("duration"),
                "duration_seconds": duration_seconds,
                "view_count": view_count,
                "is_compilation": _is_compilation(title or "", duration_seconds),
                "has_sheet_music_link": bool(links),
                "sheet_music_links": links,
                "description_excerpt": description[:500],
            },
        )
