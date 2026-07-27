"""IMSLP connector — Phase 2.

Public-domain classical scores. Confirm current IMSLP terms before building this
for real; keep requests polite and non-commercial.
"""
from __future__ import annotations

from .base import Connector
from ..models import Card


class ImslpConnector(Connector):
    source = "imslp"

    def search(self, query: str, limit: int = 20) -> list[Card]:
        raise NotImplementedError("IMSLP connector lands in Phase 2.")
