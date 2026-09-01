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


# --- when an event happened, versus when the row was written -----------------

def test_a_client_timestamp_is_used_when_it_is_sane():
    """created_at is read as chronology by training, so it should say when the thing
    happened, not when the insert ran."""
    from scorekit.store import parse_occurred_at
    assert parse_occurred_at("2026-08-30T12:00:00Z") == "2026-08-30T12:00:00+00:00"
    # A bare timestamp is taken as UTC rather than rejected.
    assert parse_occurred_at("2026-08-30T12:00:00") == "2026-08-30T12:00:00+00:00"


def test_an_implausible_client_timestamp_falls_back_to_the_server_clock():
    """A wrong client clock would otherwise reorder somebody's whole history."""
    from scorekit.store import parse_occurred_at
    assert parse_occurred_at("2030-01-01T00:00:00Z") is None   # far future
    assert parse_occurred_at("1999-01-01T00:00:00Z") is None   # before the project existed
    assert parse_occurred_at("yesterday") is None
    assert parse_occurred_at(None) is None


def test_a_mixed_batch_does_not_send_null_timestamps():
    """PostgREST builds one column list per batch, so a row omitting created_at next to
    one that sets it is sent an explicit NULL and the not-null constraint drops the whole
    batch — which cost three rows before this was handled."""
    from scorekit.store import log_events

    class _Table:
        def __init__(self, sink): self.sink = sink
        def insert(self, rows):
            self.sink.extend(rows)
            return self
        def execute(self):
            return type("R", (), {"data": self.sink})

    captured: list[dict] = []
    client = type("C", (), {"table": lambda self, _n: _Table(captured)})()
    log_events([
        {"user_id": "u", "action": "like", "occurred_at": "2026-08-14T09:30:00Z"},
        {"user_id": "u", "action": "click"},
    ], client=client)
    assert all(row.get("created_at") for row in captured)
    assert captured[0]["created_at"].startswith("2026-08-14")
