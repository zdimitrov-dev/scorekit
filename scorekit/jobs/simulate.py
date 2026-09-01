"""Generate synthetic interactions with a **known** taste, for testing the learned ranker.

Not a substitute for real data — it is a test instrument. Because the preference used to
generate the likes is written down here, we can check the trained model *recovered it*,
which a real dataset can never tell us: with real logs there is no ground truth to compare
against, only a metric that may be high for the wrong reasons.

Each persona gets a deterministic UUID derived from its name, so runs are idempotent and
the rows are trivially removable:

    python -m scorekit.jobs.simulate --sessions 6
    python -m scorekit.jobs.simulate --clear
"""
from __future__ import annotations

import argparse
import logging
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ..db import get_client
from ..store import log_events

log = logging.getLogger("scorekit.simulate")

# Stable namespace so a persona always maps to the same user_id.
_NS = uuid.UUID("5c07e100-0000-4000-8000-000000000000")

# The ground truth. Weights are how much a tag pulls toward liking; the model is judged on
# whether it rediscovers this shape from behaviour alone.
PERSONAS: dict[str, dict[tuple[str, str], float]] = {
    "romantic-pianist": {
        ("era", "romantic"): 1.2, ("composer", "chopin"): 1.6,
        ("composer", "liszt"): 1.0, ("form", "nocturne"): 1.4,
        ("form", "ballade"): 1.2, ("form", "etude"): 0.6,
    },
    "baroque-keyboardist": {
        ("era", "baroque"): 1.4, ("composer", "bach"): 1.6,
        ("composer", "scarlatti"): 0.9, ("form", "fugue"): 1.2,
        ("form", "prelude"): 0.7, ("form", "suite"): 0.8,
    },
    "impressionist-listener": {
        ("era", "impressionist"): 1.5, ("composer", "debussy"): 1.4,
        ("composer", "satie"): 1.2, ("instrumentation", "piano"): 0.4,
    },
    "classical-purist": {
        ("era", "classical"): 1.4, ("composer", "mozart"): 1.3,
        ("composer", "haydn"): 1.1, ("form", "sonata"): 1.0,
        ("form", "minuet"): 0.8,
    },
    "virtuoso-chaser": {
        ("composer", "liszt"): 1.5, ("composer", "rachmaninoff"): 1.5,
        ("form", "etude"): 1.2, ("form", "concerto"): 1.0,
        ("era", "romantic"): 0.6,
    },
    # Overlaps romantic-pianist heavily but not entirely: two people can share a taste
    # without sharing it exactly, and a model that only works on disjoint users is not
    # measuring generalisation.
    "chopin-devotee": {
        ("composer", "chopin"): 2.0, ("form", "nocturne"): 1.1,
        ("form", "mazurka"): 1.0, ("form", "waltz"): 0.9,
        ("era", "romantic"): 0.5,
    },
    "bach-completist": {
        ("composer", "bach"): 2.0, ("form", "fugue"): 1.1,
        ("form", "prelude"): 1.0, ("form", "variations"): 0.7,
        ("era", "baroque"): 0.5,
    },
    "sonata-reader": {
        ("form", "sonata"): 1.6, ("composer", "beethoven"): 1.3,
        ("composer", "clementi"): 0.9, ("era", "classical"): 0.7,
    },
    "modernist": {
        ("era", "modern"): 1.6, ("form", "rag"): 1.0,
        ("form", "variations"): 0.7, ("composer", "satie"): 0.6,
    },
    "beginner-tutorials": {
        ("format", "tutorial"): 1.8, ("composer", "clementi"): 0.9,
        ("form", "minuet"): 0.8, ("form", "prelude"): 0.6,
    },
    "performance-watcher": {
        ("format", "performance"): 1.5, ("form", "concerto"): 0.9,
        ("composer", "rachmaninoff"): 0.8, ("era", "romantic"): 0.5,
    },
    "nordic-romantic": {
        ("composer", "grieg"): 1.8, ("era", "romantic"): 0.9,
        ("form", "suite"): 0.8, ("form", "waltz"): 0.6,
    },
}

# Turns a taste score into a like probability. The offset keeps likes genuinely rare, as
# they are in a real feed — a model that only works on balanced data is not much use, and
# an easy class balance flatters every metric. Tuned to land near one positive in ten,
# which is still generous but the right order of magnitude.
_BIAS = -4.2
_SCALE = 1.5


def simulated_user_ids() -> set[str]:
    """The user ids this module writes under.

    Exposed so training can exclude them. Synthetic rows counting toward the promotion
    gate would let a model trained on a taste we invented go on to rank a real feed.
    """
    return {str(uuid.uuid5(_NS, name)) for name in PERSONAS}


def _p_like(tags: list[tuple[str, str]], persona: dict[tuple[str, str], float]) -> float:
    score = sum(persona.get(t, 0.0) for t in tags)
    return 1.0 / (1.0 + math.exp(-(_BIAS + _SCALE * score)))


def _page(sb, table: str, select: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while True:
        rows = sb.table(table).select(select).range(len(out), len(out) + 999).execute().data or []
        out += rows
        if len(rows) < 1000:
            return out


def simulate(sessions: int = 10, per_session: int = 50, seed: int = 0) -> int:
    sb = get_client()
    cards = _page(sb, "cards", "id,piece_id,source,kind,metadata")
    tags: dict[str, list[tuple[str, str]]] = {}
    for t in _page(sb, "piece_tags", "piece_id,key,value"):
        tags.setdefault(t["piece_id"], []).append((t["key"], t["value"]))
    if not cards:
        raise SystemExit("no cards to simulate against — seed the corpus first")

    rng = random.Random(seed)
    written = 0
    for name, persona in PERSONAS.items():
        user_id = str(uuid.uuid5(_NS, name))
        events: list[dict[str, Any]] = []
        # Sessions are spread over past days and events within one are seconds apart.
        # Without this every row lands at insert time, and a chronological split over a
        # single instant measures nothing — the same failure a client reconciliation
        # caused with real likes.
        first_session = datetime.now(timezone.utc) - timedelta(days=2 * sessions + 1)
        for session in range(sessions):
            session_start = first_session + timedelta(
                days=2 * session, hours=rng.uniform(0, 14))
            # A session is a screenful of the feed: everything in it is *seen*, and a few
            # are engaged with. That is what makes impressions usable as negatives.
            batch = rng.sample(cards, min(per_session, len(cards)))
            for position, card in enumerate(batch):
                occurred_at = (session_start
                               + timedelta(seconds=position * rng.uniform(2.0, 9.0)))
                piece_tags = tags.get(card["piece_id"], [])
                p = _p_like(piece_tags, persona)
                roll = rng.random()
                base = {"card_id": card["id"], "piece_id": card["piece_id"],
                        "feed_position": position,
                        "occurred_at": occurred_at.isoformat()}
                if roll < p * 0.45:
                    events.append({**base, "action": "save"})
                elif roll < p:
                    events.append({**base, "action": "like"})
                elif roll < p + 0.10:
                    # opened, and the dwell tracks how much they liked it
                    events.append({**base, "action": "click",
                                   "dwell_ms": int(rng.uniform(1200, 4000) + p * 18000)})
                else:
                    events.append({**base, "action": "seen",
                                   "dwell_ms": int(rng.uniform(900, 6000))})
        written += log_events([{**e, "user_id": user_id} for e in events])
        likes = sum(1 for e in events if e["action"] in ("like", "save"))
        log.info("%-24s user=%s  %d events, %d likes/saves", name, user_id[:8], len(events), likes)
    return written


def clear() -> int:
    sb = get_client()
    removed = 0
    for name in PERSONAS:
        user_id = str(uuid.uuid5(_NS, name))
        n = (sb.table("interactions").select("id", count="exact")
             .eq("user_id", user_id).execute().count or 0)
        sb.table("interactions").delete().eq("user_id", user_id).execute()
        removed += n
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic interactions with a known taste.")
    parser.add_argument("--sessions", type=int, default=10)
    parser.add_argument("--per-session", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--clear", action="store_true", help="delete simulated rows and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.clear:
        log.info("removed %d simulated interaction(s)", clear())
        return
    log.info("wrote %d simulated interaction(s)", simulate(args.sessions, args.per_session, args.seed))


if __name__ == "__main__":
    main()
