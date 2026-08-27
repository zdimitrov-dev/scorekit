"""Connector interface shared by every source."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Card


class ConnectorUnavailable(Exception):
    """Raised when a connector is implemented but cannot run right now — for
    example a required API key is missing. The ingest job treats this like a
    not-yet-built connector: it logs a skip instead of failing the whole run."""


class Connector(ABC):
    #: one of the ``card_source`` enum values
    source: str

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> list[Card]:
        """Return normalized cards for a piece query."""
        raise NotImplementedError
