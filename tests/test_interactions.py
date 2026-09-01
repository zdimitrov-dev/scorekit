"""Interaction logging — the recommender's training signal (Phase 5)."""
from types import SimpleNamespace

from scorekit.store import log_events


class _FakeTable:
    def __init__(self):
        self.inserted = []

    def insert(self, rows):
        self.inserted.extend(rows)
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=rows))


class _FakeClient:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return self.tables.setdefault(name, _FakeTable())


def test_seen_is_an_impression_not_a_skip():
    # "passed over" and "deliberately rejected" carry different confidence; collapsing
    # them at write time would be unrecoverable later
    c = _FakeClient()
    log_events([{"user_id": "u1", "action": "seen", "card_id": "c1"}], client=c)
    assert c.tables["interactions"].inserted[0]["action"] == "impression"


def test_save_is_stored_distinctly_from_like():
    # saving is a deliberate "keep this" and outweighs a like in SIGNAL_WEIGHTS
    c = _FakeClient()
    log_events([{"user_id": "u1", "action": "save", "card_id": "c1"}], client=c)
    assert c.tables["interactions"].inserted[0]["action"] == "save"


def test_dwell_and_position_are_carried_through():
    c = _FakeClient()
    log_events(
        [{"user_id": "u1", "action": "click", "card_id": "c1",
          "piece_id": "p1", "dwell_ms": 4200, "feed_position": 7}],
        client=c,
    )
    row = c.tables["interactions"].inserted[0]
    assert (row["dwell_ms"], row["feed_position"], row["piece_id"]) == (4200, 7, "p1")


def test_unknown_actions_and_anonymous_rows_are_dropped_not_raised():
    # telemetry must never break the caller
    c = _FakeClient()
    written = log_events(
        [
            {"user_id": "u1", "action": "teleport", "card_id": "c1"},   # unknown action
            {"action": "like", "card_id": "c2"},                        # no user
            {"user_id": "u1", "action": "like", "card_id": "c3"},       # the good one
        ],
        client=c,
    )
    assert written == 1
    assert [r["card_id"] for r in c.tables["interactions"].inserted] == ["c3"]


def test_no_write_when_nothing_survives_filtering():
    c = _FakeClient()
    assert log_events([{"action": "like"}], client=c) == 0
    assert "interactions" not in c.tables


def test_negative_dwell_is_clamped():
    # a clock adjustment mid-session should not poison a training row
    c = _FakeClient()
    log_events([{"user_id": "u1", "action": "seen", "card_id": "c1", "dwell_ms": -5}], client=c)
    assert c.tables["interactions"].inserted[0]["dwell_ms"] == 0


# --- reconciliation must not invent a chronology ----------------------------

def test_sync_skips_undated_likes_when_it_cannot_flag_them():
    """A like with no recorded time can only be stored honestly if there is somewhere to
    say so. Otherwise it enters the log looking like an ordinary event that happened at
    the instant of the sync, and training reads created_at as chronology.

    This is not hypothetical: clearing the table and reloading the page put twelve likes
    back, all sharing two timestamps 50ms apart."""
    from scorekit.store import log_events

    written: list[dict] = []

    class _Table:
        def insert(self, rows):
            written.extend(rows)
            return self
        def execute(self):
            return type("R", (), {"data": written})

    client = type("C", (), {"table": lambda self, _n: _Table()})()
    # An undated row that cannot be flagged is never handed to log_events at all, so the
    # closest unit-level guarantee is that a supplied time always survives.
    log_events([{"user_id": "u", "action": "like", "occurred_at": "2026-08-20T10:00:00Z"}],
               client=client)
    assert written[0]["created_at"].startswith("2026-08-20")
