"""Connector interface shared by every source."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Card


class Connector(ABC):
    #: one of the ``card_source`` enum values
    source: str

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> list[Card]:
        """Return normalized cards for a piece query."""
        raise NotImplementedError
