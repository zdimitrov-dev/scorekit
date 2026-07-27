"""YouTube connector — Phase 1.

Uses the official YouTube Data API. Video descriptions often already contain
sheet-music links, which is useful bonus signal to capture in ``Card.metadata``.
"""
from __future__ import annotations

from .base import Connector
from ..models import Card


class YouTubeConnector(Connector):
    source = "youtube"

    def search(self, query: str, limit: int = 20) -> list[Card]:
        raise NotImplementedError("YouTube connector lands in Phase 1.")
