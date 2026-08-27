"""IMSLP connector — Phase 2 (framework).

IMSLP (the Petrucci Music Library) hosts public-domain classical scores. This
connector searches IMSLP through its MediaWiki API
(``https://imslp.org/api.php`` with ``action=query&list=search``) and normalizes
each matching work page into a ``Card`` with ``kind="score"``.

IMSLP main-namespace work pages follow the title convention
``Work Title (Surname, Forename)``, so the composer can be recovered straight
from the result title — IMSLP is an authoritative source for classical composer
attribution, unlike the free-text YouTube path (see the "composer sourcing" open
question in PROJECT_CONTEXT).

Status: **framework, inert by default.** ``search()`` raises
``ConnectorUnavailable`` until ``IMSLP_ENABLED`` is set, so the ingest job simply
skips it — the same treatment as a not-yet-built connector. Enable it only after
confirming IMSLP's current terms of use. When enabled, keep requests polite: a
descriptive User-Agent and low volume (IMSLP is a donation-funded non-profit).

The parsing/normalization logic here is pure and unit-tested. Deliberately left
for the implementation pass (see TODOs): fetching each work page for per-file
license, direct PDF links, instrumentation, and a cover thumbnail. The live
search path is written to MediaWiki's standard contract but has **not** been
verified against IMSLP yet — do that when enabling.
"""
from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import quote

import httpx

from .base import Connector, ConnectorUnavailable
from ..config import settings
from ..models import Card

IMSLP_API = "https://imslp.org/api.php"
WIKI_BASE = "https://imslp.org/wiki/"
# MediaWiki etiquette: identify the client. Points at the repo so IMSLP admins
# can see who is calling if they ever need to.
USER_AGENT = "scorekit/0.0 (+https://github.com/zdimitrov-dev/scorekit)"

# IMSLP work-page titles: "Work Title (Surname, Forename)".
_TITLE_RE = re.compile(r"^(?P<title>.+?)\s*\((?P<last>[^,()]+),\s*(?P<first>[^()]+)\)\s*$")
# Strip the <span class="searchmatch">…</span> markup MediaWiki puts in snippets.
_TAG_RE = re.compile(r"<[^>]+>")


def _parse_title(page_title: str) -> tuple[str, str | None]:
    """Split an IMSLP page title into ``(work_title, composer)``.

    >>> _parse_title("Clair de lune (Debussy, Claude)")
    ('Clair de lune', 'Claude Debussy')

    Titles that do not match the convention return ``(title, None)``.
    """
    m = _TITLE_RE.match(page_title.strip())
    if not m:
        return page_title.strip(), None
    composer = f"{m.group('first').strip()} {m.group('last').strip()}"
    return m.group("title").strip(), composer


def _work_url(page_title: str) -> str:
    """Canonical IMSLP wiki URL for a page title (spaces -> underscores)."""
    return WIKI_BASE + quote(page_title.replace(" ", "_"), safe="(),_-")


def _strip_html(text: str) -> str:
    """Plain text from a MediaWiki search snippet (drops tags, unescapes entities)."""
    return unescape(_TAG_RE.sub("", text or "")).strip()


class ImslpConnector(Connector):
    source = "imslp"

    def __init__(self, client: Any = None) -> None:
        # An httpx-like client can be injected (tests); otherwise built lazily.
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15.0)
        return self._client

    def search(self, query: str, limit: int = 20) -> list[Card]:
        if not settings.imslp_enabled:
            raise ConnectorUnavailable(
                "IMSLP connector is disabled — set IMSLP_ENABLED=1 after confirming "
                "IMSLP's terms of use (see .env.example)."
            )
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srnamespace": 0,            # main namespace = work pages
            "srlimit": max(1, min(limit, 50)),
            "format": "json",
        }
        resp = self.client.get(IMSLP_API, params=params)
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])

        cards: list[Card] = []
        for r in results:
            card = self._to_card(r)
            if card is not None:
                cards.append(card)
        return cards

    def _to_card(self, result: dict) -> Card | None:
        page_title = result.get("title")
        if not page_title:
            return None
        work_title, composer = _parse_title(page_title)
        return Card(
            source=self.source,
            external_id=str(result.get("pageid") or page_title),
            url=_work_url(page_title),
            title=work_title,
            kind="score",
            thumbnail_url=None,      # TODO(enrich): fetch work page for a cover thumbnail
            author=composer,         # composer/arranger; IMSLP is authoritative for classical
            metadata={
                "imslp_page_title": page_title,
                "pageid": result.get("pageid"),
                "composer": composer,
                "snippet": _strip_html(result.get("snippet", "")),
                # TODO(enrich): per-file license (many are Public Domain / CC),
                # direct PDF download links, instrumentation, arranger.
            },
        )
