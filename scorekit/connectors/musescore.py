"""MuseScore connector — Phase 3.

Uses Google Custom Search restricted to ``site:musescore.com``, cached per piece.
We never touch MuseScore's servers directly — only link out to results a search
engine already indexed.
"""
from __future__ import annotations

from .base import Connector
from ..models import Card


class MuseScoreConnector(Connector):
    source = "musescore"

    def search(self, query: str, limit: int = 20) -> list[Card]:
        raise NotImplementedError("MuseScore connector lands in Phase 3.")
