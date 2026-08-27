from scorekit.models import Card, Piece
from scorekit.store import upsert_cards, upsert_piece


# --- a minimal stand-in for the supabase client's table().upsert().execute() --
class _Resp:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls
        self._payload = None

    def upsert(self, payload, on_conflict=None):
        self._payload = payload
        self.calls.append((self.name, payload, on_conflict))
        return self

    def execute(self):
        if self.name == "pieces":
            return _Resp([{"id": "piece-uuid-1"}])
        rows = self._payload if isinstance(self._payload, list) else [self._payload]
        return _Resp(rows)


class _FakeClient:
    def __init__(self):
        self.calls = []

    def table(self, name):
        return _FakeTable(name, self.calls)


def test_upsert_piece_returns_id_and_drops_nones():
    client = _FakeClient()
    pid = upsert_piece(
        Piece(slug="debussy-clair-de-lune", title="Clair de Lune", composer="Debussy"),
        client=client,
    )
    assert pid == "piece-uuid-1"
    name, payload, on_conflict = client.calls[0]
    assert name == "pieces"
    assert on_conflict == "slug"
    assert payload["slug"] == "debussy-clair-de-lune"
    assert payload["composer"] == "Debussy"
    assert "era" not in payload  # None fields dropped


def test_upsert_cards_maps_rows():
    client = _FakeClient()
    cards = [
        Card(source="youtube", external_id="abc", url="https://y/abc",
             title="T", kind="tutorial", metadata={"k": 1})
    ]
    n = upsert_cards("piece-uuid-1", cards, client=client)
    assert n == 1
    name, payload, on_conflict = client.calls[0]
    assert name == "cards"
    assert on_conflict == "source,external_id"
    assert payload[0]["piece_id"] == "piece-uuid-1"
    assert payload[0]["external_id"] == "abc"
    assert payload[0]["metadata"] == {"k": 1}


def test_upsert_cards_empty_is_noop():
    client = _FakeClient()
    assert upsert_cards("pid", [], client=client) == 0
    assert client.calls == []
