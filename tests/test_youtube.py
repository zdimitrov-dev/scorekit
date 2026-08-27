from types import SimpleNamespace

import pytest

from scorekit.connectors import youtube
from scorekit.connectors.base import ConnectorUnavailable
from scorekit.connectors.youtube import (
    YouTubeConnector,
    _classify_kind,
    _extract_sheet_links,
)


# --- a minimal stand-in for the google-api-python-client fluent interface ----
class _FakeReq:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class _FakeSearchResource:
    def __init__(self, response):
        self._response = response

    def list(self, **kwargs):
        return _FakeReq(self._response)


class _FakeClient:
    def __init__(self, response):
        self._response = response

    def search(self):
        return _FakeSearchResource(self._response)


SAMPLE = {
    "items": [
        {
            "id": {"kind": "youtube#video", "videoId": "abc123"},
            "snippet": {
                "title": "Chopin &amp; Liszt Nocturne (Piano Tutorial)",
                "description": "Get the sheet music: https://musescore.com/u/1/s/2 . Enjoy!",
                "channelId": "CH1",
                "channelTitle": "Piano Time",
                "publishedAt": "2020-01-01T00:00:00Z",
                "thumbnails": {
                    "default": {"url": "https://img/def.jpg"},
                    "high": {"url": "https://img/high.jpg"},
                },
            },
        },
        {  # not a video -> no videoId -> should be skipped
            "id": {"kind": "youtube#channel", "channelId": "CHX"},
            "snippet": {"title": "A channel"},
        },
    ]
}


def test_classify_kind():
    assert _classify_kind("Moonlight Sonata - Piano Tutorial") == "tutorial"
    assert _classify_kind("Someone plays a cover of Clair de Lune") == "cover"
    assert _classify_kind("Live performance at Carnegie Hall") == "performance"
    assert _classify_kind("Clair de Lune") is None


def test_extract_sheet_links():
    desc = "sheets https://musescore.com/x and https://imslp.org/y plus https://example.com/z"
    links = _extract_sheet_links(desc)
    assert "https://musescore.com/x" in links
    assert "https://imslp.org/y" in links
    assert "https://example.com/z" not in links


def test_search_normalizes_and_skips_non_videos():
    conn = YouTubeConnector(client=_FakeClient(SAMPLE))
    cards = conn.search("nocturne", limit=10)

    assert len(cards) == 1
    card = cards[0]
    assert card.source == "youtube"
    assert card.external_id == "abc123"
    assert card.url == "https://www.youtube.com/watch?v=abc123"
    assert card.kind == "tutorial"
    assert card.title == "Chopin & Liszt Nocturne (Piano Tutorial)"  # HTML unescaped
    assert card.thumbnail_url == "https://img/high.jpg"               # prefers 'high'
    assert card.author == "Piano Time"
    assert card.metadata["has_sheet_music_link"] is True
    assert card.metadata["sheet_music_links"] == ["https://musescore.com/u/1/s/2"]


def test_missing_api_key_raises_connector_unavailable(monkeypatch):
    monkeypatch.setattr(youtube, "settings", SimpleNamespace(youtube_api_key=""))
    with pytest.raises(ConnectorUnavailable):
        YouTubeConnector().search("anything")
