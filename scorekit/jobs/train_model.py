"""Train the learned ranker and report it against the hand-tuned heuristic.

    python -m scorekit.jobs.train_model
    python -m scorekit.jobs.train_model --user <uuid>
"""
from __future__ import annotations

import argparse
import logging
from typing import Any

from ..db import get_client
from ..ml.dataset import build_dataset, label_summary
from ..ml.features import corpus_weights
from ..ml.registry import gate, save_model
from ..ml.train import heuristic_baseline, train_all

log = logging.getLogger("scorekit.train")


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
    parser = argparse.ArgumentParser(description="Train and evaluate the learned ranker.")
    parser.add_argument("--user", help="restrict to one user id")
    parser.add_argument("--test-frac", type=float, default=0.3)
    parser.add_argument("--top-features", type=int, default=10)
    parser.add_argument("--mode", choices=["chronological", "cross_user", "both"],
                        default="both", help="how to hold out the test rows")
    parser.add_argument("--promote", action="store_true",
                        help="save the best fit for the feed to use, if it passes the gate")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    sb = get_client()
    kw = {"user_id": args.user} if args.user else {}
    events = _page(sb, "interactions",
                   "id,user_id,action,card_id,piece_id,dwell_ms,feed_position,created_at", **kw)
    cards = {c["id"]: c for c in _page(sb, "cards", "id,piece_id,source,kind,metadata")}
    tags: dict[str, list[tuple[str, str]]] = {}
    for t in _page(sb, "piece_tags", "piece_id,key,value"):
        tags.setdefault(t["piece_id"], []).append((t["key"], t["value"]))

    log.info("%d interactions, %d cards, %d tagged pieces", len(events), len(cards), len(tags))
    data = build_dataset(events, cards, tags, corpus_weights(tags))
    log.info("dataset: %s\n", label_summary(data))
    if data.positives == 0:
        raise SystemExit(
            "No positive examples. Browse the feed and like some pieces, or generate a "
            "synthetic taste with: python -m scorekit.jobs.simulate"
        )

    modes = ["chronological", "cross_user"] if args.mode == "both" else [args.mode]
    last: list = []
    for mode in modes:
        label = ("same users, their later behaviour" if mode == "chronological"
                 else "users held out entirely — never seen in training")
        log.info("\n=== %s — %s ===", mode, label)
        results = train_all(data, args.test_frac, mode)
        baseline = heuristic_baseline(data, args.test_frac, mode)
        log.info("%-26s %8s %14s", "model", "ROC-AUC", "precision@10")
        log.info("%s", "-" * 52)
        for r in [baseline, *sorted(results, key=lambda r: -(r.auc if r.auc == r.auc else 0))]:
            log.info("%-26s %8.3f %14.3f", r.name, r.auc, r.precision_at_10)
        last = results

    for r in last:
        if not r.importances:
            continue
        log.info("\n%s — what it leaned on:", r.name)
        for feat, val in r.importances[:args.top_features]:
            log.info("   %-28s %+.4f", feat, val)


if __name__ == "__main__":
    main()
