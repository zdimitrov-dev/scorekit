"""Rank the corpus twice, by the heuristic and by the saved model, side by side.

The point of testing a ranker is judging whether it is *better*, and a single list cannot
answer that. Both columns are built from the same history and the same corpus, so any
difference is the ranker and nothing else.

Works with a model that has not passed the gate, which is the whole reason to look.

    python -m scorekit.jobs.compare
    python -m scorekit.jobs.compare --user <uuid> --top 15
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from ..db import get_client
from ..ml.registry import model_info
from ..ml.serve import score_cards
from ..recommend import SIGNAL_WEIGHTS, idf_weights, rank_cards

log = logging.getLogger("scorekit.compare")


def _page(sb, table: str, select: str, **eq) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while True:
        q = sb.table(table).select(select)
        for k, v in eq.items():
            q = q.eq(k, v)
        rows = q.range(len(out), len(out) + 999).execute().data or []
        out += rows
        if len(rows) < 1000:
            return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Heuristic vs model, side by side.")
    parser.add_argument("--user", help="whose history to rank for; default: the busiest")
    parser.add_argument("--top", type=int, default=12)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    info = model_info()
    if not info["available"]:
        raise SystemExit("No saved model. Run: python -m scorekit.jobs.train_model --force")
    log.info("model: %s  auc %.3f  promoted=%s", info.get("name"),
             info.get("auc", float("nan")), info["promoted"])

    sb = get_client()
    events = _page(sb, "interactions", "user_id,action,card_id,piece_id,dwell_ms")
    cards = _page(sb, "cards", "id,piece_id,source,kind,title,author,metadata")
    by_id = {c["id"]: c for c in cards}
    pieces = {p["id"]: p for p in _page(sb, "pieces", "id,slug,composer")}
    tags: dict[str, list[tuple[str, str]]] = {}
    for t in _page(sb, "piece_tags", "piece_id,key,value"):
        tags.setdefault(t["piece_id"], []).append((t["key"], t["value"]))

    user = args.user
    if not user:
        counts: dict[str, int] = {}
        for e in events:
            if e["action"] in ("like", "save"):
                counts[e["user_id"]] = counts.get(e["user_id"], 0) + 1
        if not counts:
            raise SystemExit("Nobody has liked anything yet, so there is nothing to rank for.")
        user = max(counts, key=counts.get)

    signals = [(e["piece_id"] or (by_id.get(e["card_id"] or "") or {}).get("piece_id"), e["action"])
               for e in events
               if e["user_id"] == user and e["action"] in ("like", "save")]
    positives = [(pid, SIGNAL_WEIGHTS.get(a, 0.0)) for pid, a in signals if pid]
    log.info("ranking for %s, built from %d likes/saves\n", user[:8], len(positives))

    weights = idf_weights(tags)
    relevance = score_cards(cards, tags, weights, positives, force=True)
    if relevance is None:
        raise SystemExit("The model declined to score (no history, or it failed to load).")

    def ranked(rel):
        return rank_cards(cards, tags, signals=signals, limit=args.top, relevance=rel)

    left = ranked(None)
    right = ranked(relevance)

    def label(card):
        piece = pieces.get(card.get("piece_id"), {})
        who = piece.get("composer") or card.get("author") or "?"
        return f"{who[:16]:16} {(card.get('title') or '')[:30]}"

    log.info("%-49s | %s", "HEURISTIC (what the feed uses now)", "MODEL (saved, not promoted)")
    log.info("%s", "-" * 100)
    same = 0
    for i in range(max(len(left), len(right))):
        a = label(left[i]) if i < len(left) else ""
        b = label(right[i]) if i < len(right) else ""
        if i < len(left) and i < len(right) and left[i]["id"] == right[i]["id"]:
            same += 1
        log.info("%-49s | %s", a, b)

    overlap = len({c["id"] for c in left} & {c["id"] for c in right})
    log.info("\n%d of %d in the same position; %d of %d cards appear in both",
             same, min(len(left), len(right)), overlap, min(len(left), len(right)))


if __name__ == "__main__":
    main()
