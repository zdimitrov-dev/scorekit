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
    parser.add_argument("--force", action="store_true",
                        help="save it even if the gate fails, for testing; the feed will "
                             "not use it unless asked for by name")
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
        log.info("\n%s: what it leaned on", r.name)
        for feat, val in r.importances[:args.top_features]:
            log.info("   %-28s %+.4f", feat, val)

    # Promotion is judged on the chronological split, which is the production question:
    # given what this person has done so far, what will they engage with next.
    scored = train_all(data, args.test_frac, "chronological")
    base = heuristic_baseline(data, args.test_frac, "chronological")
    best = max(scored, key=lambda r: r.auc if r.auc == r.auc else -1)
    ok, reason = gate(best.auc, base.auc, data.positives)

    log.info("\nGate: best is %s. %s", best.name, reason)
    if not ok and not args.force:
        log.info("Not promoted. The feed keeps using the content ranker.")
        log.info("To try it anyway: --force, then request it with ranker=model.")
        return
    if not (args.promote or args.force):
        log.info("Passes the gate. Re-run with --promote to serve it.")
        return

    path = save_model(best.model, data.feature_names, {
        "name": best.name,
        "passed_gate": ok,
        "gate_reason": reason,
        "auc": best.auc,
        "heuristic_auc": base.auc,
        "precision_at_10": best.precision_at_10,
        "n_train": best.n_train,
        "n_test": best.n_test,
        "positives": data.positives,
        "feature_names": data.feature_names,
    })
    if ok:
        log.info("Promoted %s to %s. The feed will use it.", best.name, path)
    else:
        log.info("Saved %s to %s for testing only.", best.name, path)
        log.info("The feed still uses the content ranker; request ranker=model to try it.")


if __name__ == "__main__":
    main()
