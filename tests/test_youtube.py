from types import SimpleNamespace

import pytest

from scorekit.connectors import youtube
from scorekit.connectors.base import ConnectorUnavailable
from scorekit.connectors.youtube import (
    YouTubeConnector,
    _classify_kind,
    _extract_sheet_links,
    _is_compilation,
    _is_topic_channel,
    _parse_duration,
)


# --- fakes for the two-step google-api-python-client fluent interface --------
class _FakeReq:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class _FakeResource:
    def __init__(self, response):
        self._response = response

    def list(self, **kwargs):
        return _FakeReq(self._response)


class _FakeClient:
    def __init__(self, search_response, videos_response):
        self._search = search_response
        self._videos = videos_response

    def search(self):
        return _FakeResource(self._search)

    def videos(self):
        return _FakeResource(self._videos)


SEARCH_RESP = {
    "items": [
        {"id": {"kind": "youtube#video", "videoId": "abc123"}},
        {"id": {"kind": "youtube#channel", "channelId": "CHX"}},  # skipped: no videoId
        {"id": {"kind": "youtube#video", "videoId": "long1"}},
        {"id": {"kind": "youtube#video", "videoId": "topic1"}},   # dropped: - Topic channel
    ]
}

VIDEOS_RESP = {
    "items": [
        {
            "id": "abc123",
            "snippet": {
                "title": "Chopin &amp; Liszt Nocturne (Piano Tutorial)",
                "description": "Enjoy! Sheet music here: https://musescore.com/u/1/s/2 -- thanks",
                "channelId": "CH1",
                "channelTitle": "Piano Time",
                "publishedAt": "2020-01-01T00:00:00Z",
                "thumbnails": {
                    "default": {"url": "https://img/def.jpg"},
                    "high": {"url": "https://img/high.jpg"},
                },
            },
            "contentDetails": {"duration": "PT8M30S"},
            "statistics": {"viewCount": "12345"},
        },
        {
            "id": "long1",
            "snippet": {
                "title": "4 HOURS Clair de Lune Relaxation",
                "description": "relax",
                "channelId": "CH2",
                "channelTitle": "Lullaby",
                "publishedAt": "2021-01-01T00:00:00Z",
                "thumbnails": {},
            },
            "contentDetails": {"duration": "PT4H0M0S"},
            "statistics": {"viewCount": "999"},
        },
        {
            "id": "topic1",
            "snippet": {
                "title": "Clair de Lune",
                "description": "",
                "channelId": "CH3",
                "channelTitle": "Claude Debussy - Topic",
                "publishedAt": "2019-01-01T00:00:00Z",
                "thumbnails": {},
            },
            "contentDetails": {"duration": "PT5M0S"},
            "statistics": {"viewCount": "5000"},
        },
    ]
}


def test_parse_duration():
    assert _parse_duration("PT8M30S") == 510
    assert _parse_duration("PT4H0M0S") == 14400
    assert _parse_duration("PT45S") == 45
    assert _parse_duration("P1DT2H") == 93600
    assert _parse_duration("garbage") is None
    assert _parse_duration(None) is None


def test_classify_kind():
    assert _classify_kind("Moonlight Sonata - Piano Tutorial") == "tutorial"
    assert _classify_kind("A cover of Clair de Lune") == "cover"
    assert _classify_kind("Live at Carnegie Hall") == "performance"
    assert _classify_kind("Clair de Lune") is None


def test_is_topic_channel():
    assert _is_topic_channel("Claude Debussy - Topic") is True
    assert _is_topic_channel("claude debussy - topic") is True
    assert _is_topic_channel("Rousseau") is False
    assert _is_topic_channel(None) is False


def test_is_compilation():
    assert _is_compilation("Debussy Nocturne", 510) is False
    assert _is_compilation("Debussy Nocturne", 1200) is True             # long enough
    assert _is_compilation("Best of Chopin (Mix)", 300) is True          # standalone 'mix'
    assert _is_compilation("Clair de Lune Ethereal Remix", 274) is False # 'remix' != 'mix'
    assert _is_compilation("4 Hours of Piano", 60) is True               # 'hours' cue


def test_extract_sheet_links():
    desc = "sheets https://musescore.com/x and https://imslp.org/y plus https://example.com/z"
    links = _extract_sheet_links(desc)
    assert "https://musescore.com/x" in links
    assert "https://imslp.org/y" in links
    assert "https://example.com/z" not in links


def test_search_enriches_skips_non_videos_and_topic_channels():
    conn = YouTubeConnector(client=_FakeClient(SEARCH_RESP, VIDEOS_RESP))
    cards = conn.search("nocturne", limit=10)

    # relevance order kept; non-video AND the "- Topic" channel are dropped
    assert [c.external_id for c in cards] == ["abc123", "long1"]
    assert "topic1" not in [c.external_id for c in cards]

    first = cards[0]
    assert first.kind == "tutorial"
    assert first.title == "Chopin & Liszt Nocturne (Piano Tutorial)"   # HTML unescaped
    assert first.thumbnail_url == "https://img/high.jpg"               # prefers 'high'
    assert first.metadata["duration_seconds"] == 510
    assert first.metadata["view_count"] == 12345
    assert first.metadata["is_compilation"] is False
    assert first.metadata["has_sheet_music_link"] is True              # from FULL description
    assert first.metadata["sheet_music_links"] == ["https://musescore.com/u/1/s/2"]

    second = cards[1]
    assert second.metadata["duration_seconds"] == 14400
    assert second.metadata["is_compilation"] is True                   # 4 hours


def test_missing_api_key_raises_connector_unavailable(monkeypatch):
    monkeypatch.setattr(youtube, "settings", SimpleNamespace(youtube_api_key=""))
    with pytest.raises(ConnectorUnavailable):
        YouTubeConnector().search("anything")
