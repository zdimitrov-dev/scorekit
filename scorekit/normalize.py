"""Normalization helpers.

The canonical ``pieces.slug`` is what lets cards from different sources attribute
signal to the same real piece without ever being merged in the feed.
"""
from __future__ import annotations

import re
import unicodedata


def normalize_slug(title: str, composer: str | None = None) -> str:
    """Build a stable, ASCII slug from composer + title.

    >>> normalize_slug("Clair de Lune", "Debussy")
    'debussy-clair-de-lune'
    """
    raw = " ".join(p for p in (composer, title) if p)
    raw = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    raw = raw.lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return raw
