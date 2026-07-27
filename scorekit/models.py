"""Shared, source-agnostic result schema.

Every connector normalizes its provider-specific response into a ``Card`` before
anything else in the pipeline touches it. Persisted to the ``cards`` table.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Card:
    source: str                      # 'youtube' | 'imslp' | 'musescore'
    external_id: str                 # provider id (video id, imslp page, url hash)
    url: str
    title: str | None = None
    kind: str | None = None          # 'tutorial' | 'cover' | 'performance' | 'score' | 'listing'
    thumbnail_url: str | None = None
    author: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Piece:
    slug: str                        # normalized dedupe key
    title: str
    composer: str | None = None
    era: str | None = None
    genre: str | None = None
    difficulty: int | None = None
