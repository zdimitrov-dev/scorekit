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

Gated by ``IMSLP_ENABLED``: ``search()`` raises ``ConnectorUnavailable`` until it
is set, so the ingest job skips it. Search is verified live against IMSLP; keep
requests polite (descriptive User-Agent, low volume — IMSLP is a donation-funded
non-profit).

``enrich(card)`` is an optional second step: it fetches the card's work page and
adds per-file license (Public Domain / Creative Commons), instrumentation, piece
style, and year to ``card.metadata`` (one extra request per card).

``enrich_cards(cards)`` enriches a whole batch and additionally **resolves
disambiguation pages**: a signpost page like the Debussy "Clair de lune" (which
holds no scores — it points at Suite bergamasque and two songs) is replaced by the
real work-page cards it links to, each keeping the searched-piece title but pointing
at the actual score page. First-page score thumbnails are resolved via the MediaWiki
``imageinfo`` API when a work page has one. Not yet extracted: direct PDF download
links (IMSLP serves those through a disclaimer-gated hashed file system).
"""
from __future__ import annotations

import logging
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

log = logging.getLogger("scorekit.imslp")

# IMSLP work-page titles: "Work Title (Surname, Forename)".
_TITLE_RE = re.compile(r"^(?P<title>.+?)\s*\((?P<last>[^,()]+),\s*(?P<first>[^()]+)\)\s*$")
# Strip the <span class="searchmatch">…</span> markup MediaWiki puts in snippets.
_TAG_RE = re.compile(r"<[^>]+>")
# Templates on a disambiguation page that link to real work pages, e.g.
# {{LinkWorkN|Suite bergamasque|CD 82|Debussy|Claude|0}} -> the page
# "Suite bergamasque, CD 82 (Debussy, Claude)". {{LinkName|...}} (people) is not matched.
_LINKWORK_RE = re.compile(r"\{\{LinkWork(?:N)?\|([^{}]*)\}\}")
# Cap on how many works a single disambiguation page expands into.
MAX_DISAMBIG_TARGETS = 5


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


def _disambiguation_targets(wt: str) -> list[str]:
    """Real work-page titles a disambiguation page points to, from its
    ``LinkWork`` / ``LinkWorkN`` templates.

    >>> _disambiguation_targets("{{LinkWorkN|Suite bergamasque|CD 82|Debussy|Claude|0}}")
    ['Suite bergamasque, CD 82 (Debussy, Claude)']
    """
    targets: list[str] = []
    for inner in _LINKWORK_RE.findall(wt):
        args = [a.strip() for a in inner.split("|")]
        if len(args) < 4 or not (args[0] and args[2] and args[3]):
            continue
        title, cat, last, first = args[0], args[1], args[2], args[3]
        page = (f"{title}, {cat}" if cat else title) + f" ({last}, {first})"
        if page not in targets:
            targets.append(page)
    return targets


def _wikitext_field(wt: str, name: str) -> str | None:
    """Extract a single ``|Field=value`` value from an IMSLP page template."""
    m = re.search(r"\|\s*" + re.escape(name) + r"\s*=\s*([^|\n}]*)", wt)
    val = m.group(1).strip() if m else ""
    return val or None


def _first_score_thumb(wt: str) -> str | None:
    """The ``Thumb Filename`` of the first score file (``#fte:imslpfile`` block) —
    a first-page preview of the sheet music. Ignores audio blocks, whose thumbs are
    often stale/reused."""
    for block in wt.split("{{#fte:")[1:]:
        if block.startswith("imslpfile"):
            m = re.search(r"\|\s*Thumb Filename\s*=\s*([^|\n}]+)", block)
            if m and m.group(1).strip():
                return m.group(1).strip()
    return None


def parse_workpage(wt: str) -> dict:
    """Pull enrichment fields out of an IMSLP work page's wikitext.

    Work pages are ``{{#fte:imslppage ...}}`` templates with per-file
    ``|Copyright=`` values and a General Information block (Instrumentation, Piece
    Style, ...). Disambiguation / redirect pages have no such template — those are
    flagged instead of parsed (the famous Debussy "Clair de lune" is one: it points
    at the Suite bergamasque page rather than holding scores itself).
    """
    out: dict = {"enriched": True}
    if "#fte:imslppage" not in wt:
        out["is_work_page"] = False
        targets = _disambiguation_targets(wt)
        out["is_disambiguation"] = bool(targets) or ("can refer to" in wt.lower())
        if targets:
            out["disambiguation_targets"] = targets
        return out

    out["is_work_page"] = True
    out["has_scores"] = "#fte:imslpfile" in wt   # score files use the imslpfile template
    thumb = _first_score_thumb(wt)
    if thumb:
        out["thumb_filename"] = thumb
    for key, field in (
        ("instrumentation", "Instrumentation"),
        ("piece_style", "Piece Style"),
        ("year", "Year/Date of Composition"),
        ("opus_catalogue", "Opus/Catalogue Number"),
    ):
        val = _wikitext_field(wt, field)
        if val:
            out[key] = val

    licenses = sorted(
        {m.strip() for m in re.findall(r"\|\s*Copyright\s*=\s*([^|\n}]+)", wt) if m.strip()}
    )
    if licenses:
        out["licenses"] = licenses
        out["is_public_domain"] = any(x.lower().startswith("public domain") for x in licenses)
    return out


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
        snippet = _strip_html(result.get("snippet", ""))
        # IMSLP search also returns redirect pages; a redirect points at a real
        # work page rather than being one, so skip it (its content is "#REDIRECT
        # [[Target]]"). Verified live: these otherwise leak in as duplicate cards.
        if snippet.upper().startswith("#REDIRECT"):
            return None
        work_title, composer = _parse_title(page_title)
        return Card(
            source=self.source,
            # IMSLP's search response omits pageid, so the canonical page title —
            # stable and unique — is the external_id / dedup key.
            external_id=page_title,
            url=_work_url(page_title),
            title=work_title,
            kind="score",
            thumbnail_url=None,      # TODO(enrich): fetch work page for a cover thumbnail
            author=composer,         # composer/arranger; IMSLP is authoritative for classical
            metadata={
                "imslp_page_title": page_title,
                "composer": composer,
                "snippet": snippet,
            },
        )

    def enrich(self, card: Card) -> Card:
        """Fetch the card's work page and merge license / instrumentation / style /
        year into ``card.metadata`` (one extra request). Best-effort and in-place:
        on any failure the card is left as-is with ``metadata['enriched'] = False``.
        """
        if card.source != self.source:
            return card
        page = card.metadata.get("imslp_page_title") or card.title
        try:
            wt = self._fetch_wikitext(page)
        except Exception as exc:            # network / missing page / bad payload
            log.warning("[imslp] enrich failed for %r: %s", page, exc)
            card.metadata["enriched"] = False
            return card
        card.metadata.update(parse_workpage(wt))
        # Resolve a real first-page score thumbnail if the page has one.
        thumb = card.metadata.get("thumb_filename")
        if thumb and not card.thumbnail_url:
            card.thumbnail_url = self._resolve_thumbnail(thumb)
        return card

    def _resolve_thumbnail(self, filename: str) -> str | None:
        """Resolve an IMSLP ``File:`` thumbnail name to its image URL via imageinfo."""
        try:
            resp = self.client.get(IMSLP_API, params={
                "action": "query",
                "titles": f"File:{filename}",
                "prop": "imageinfo",
                "iiprop": "url",
                "format": "json",
            })
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values()), {})
            url = (page.get("imageinfo") or [{}])[0].get("url")
            if url and url.startswith("//"):   # IMSLP returns protocol-relative URLs
                url = "https:" + url
            return url
        except Exception as exc:
            log.warning("[imslp] thumbnail resolve failed for %r: %s", filename, exc)
            return None

    def _fetch_wikitext(self, page_title: str) -> str:
        resp = self.client.get(IMSLP_API, params={
            "action": "parse",
            "page": page_title,
            "prop": "wikitext",
            "redirects": 1,             # follow "Suite bergamasque" -> "..., CD 82"
            "format": "json",
        })
        resp.raise_for_status()
        return resp.json()["parse"]["wikitext"]["*"]

    def enrich_cards(self, cards: list[Card]) -> list[Card]:
        """Enrich IMSLP cards and **resolve disambiguation pages**.

        Each IMSLP card is enriched in place. A card whose page is a disambiguation
        (e.g. the Debussy "Clair de lune" signpost, which holds no scores) is
        *replaced* by the real work-page cards it points to — each keeping the
        searched-piece title but linking to the actual score page and carrying its
        own enrichment. Non-IMSLP cards pass through unchanged.
        """
        out: list[Card] = []
        for card in cards:
            if card.source != self.source:
                out.append(card)
                continue
            self.enrich(card)
            targets = card.metadata.get("disambiguation_targets") or []
            if card.metadata.get("is_disambiguation") and targets:
                resolved = [self._resolved_card(card, t) for t in targets[:MAX_DISAMBIG_TARGETS]]
                for rc in resolved:
                    self.enrich(rc)
                log.info("[imslp] resolved disambiguation %r -> %d work page(s)",
                         card.metadata.get("imslp_page_title"), len(resolved))
                out.extend(resolved)
            else:
                out.append(card)
        return out

    def _resolved_card(self, original: Card, target_title: str) -> Card:
        """A score card for ``target_title`` that inherits the searched-piece title
        from the disambiguation card (so it stays query-relevant) but links to the
        real work page."""
        work_title, composer = _parse_title(target_title)
        author = original.author or composer
        md = {
            "imslp_page_title": target_title,
            "composer": author,
            "resolved_from_disambiguation": (original.metadata or {}).get("imslp_page_title"),
            "parent_work": work_title,
        }
        score = (original.metadata or {}).get("match_score")
        if score is not None:
            md["match_score"] = score
        return Card(
            source=self.source,
            external_id=target_title,       # dedup on the real page
            url=_work_url(target_title),
            title=original.title,           # keep the searched-piece name
            kind="score",
            author=author,
            metadata=md,
        )
