"""Source connectors. Each returns a list of source-agnostic ``Card`` objects."""
from __future__ import annotations

from .base import Connector
from .imslp import ImslpConnector
from .musescore import MuseScoreConnector
from .youtube import YouTubeConnector

# Registry the ingest job iterates over. Add connectors here as phases land.
CONNECTORS: list[type[Connector]] = [
    YouTubeConnector,   # Phase 1
    ImslpConnector,     # Phase 2
    MuseScoreConnector, # Phase 3
]

__all__ = [
    "Connector",
    "YouTubeConnector",
    "ImslpConnector",
    "MuseScoreConnector",
    "CONNECTORS",
]
