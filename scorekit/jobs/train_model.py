"""Train the learned ranker and report it against the hand-tuned heuristic.

    python -m scorekit.jobs.train_model
    python -m scorekit.jobs.train_model --tune --force
    python -m scorekit.jobs.train_model --simulated only

The run itself lives in ``ml.pipeline`` so this command and the dev dashboard's retrain
button cannot drift apart. What is here is argument parsing and how the result is printed.
"""
from __future__ import annotations

import argparse
import logging

from ..ml.dataset import build_dataset, label_summary
from ..ml.features import corpus_weights
from ..ml.pipeline import load_training_data, run_training
from ..ml.train import heuristic_baseline, train_all, tune_forest

log = logging.getLogger("scorekit.train")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate the learned ranker.")
    parser.add_argument("--user", help="restrict to one user id")
    parser.add_argument("--test-frac", type=float, default=0.3)
    parser.add_argument("--top-features", type=int, default=10)
    parser.add_argument("--mode", choices=["chronological", "cross_user", "both"],
                        default="both", help="how to hold out the test rows")
    parser.add_argument("--promote", action="store_true",
                        help="save the best fit for the feed to use, if it passes the gate")
    parser.add_argument("--simulated", choices=["exclude", "include", "only"],
                        default="exclude",
                        help="what to do with rows written by jobs.simulate; excluded by "
                             "default so a synthetic taste can never promote a model")
    parser.add_argument("--tune", action="store_true",
                        help="cross-validate forest hyperparameters instead of the "
                             "hand-picked ones")
    parser.add_argument("--tune-iters", type=int, default=40,
                        help="how many hyperparameter combinations to try")
    parser.add_argument("--force", action="store_true",
                        help="save it even if the gate fails, for testing; the feed will "
                             "not use it unless asked for by name")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Both splits are reported even though only the chronological one decides promotion:
    # the gap between them is what says whether the model generalises to somebody it has
    # never seen, or has only learned the users it was handed.
    events, cards, tags, dropped = load_training_data(args.user, args.simulated)
    data = build_dataset(events, cards, tags, corpus_weights(tags))
    log.info("%d interactions, %d cards, %d tagged pieces", len(events), len(cards), len(tags))
    if dropped:
        log.info("(%d simulated rows excluded; --simulated %s)", dropped, args.simulated)
    log.info("dataset: %s", label_summary(data))
    if data.positives == 0:
        raise SystemExit(
            "No positive examples. Browse the feed and like some pieces, or generate a "
            "synthetic taste with: python -m scorekit.jobs.simulate"
        )

    modes = ["chronological", "cross_user"] if args.mode == "both" else [args.mode]
    for mode in modes:
        label = ("same users, their later behaviour" if mode == "chronological"
                 else "users held out entirely — never seen in training")
        log.info("\n=== %s — %s ===", mode, label)
        results = train_all(data, args.test_frac, mode)
        if args.tune:
            tuned = tune_forest(data, args.test_frac, mode, args.tune_iters)
            if tuned is not None:
                results.append(tuned)
        baseline = heuristic_baseline(data, args.test_frac, mode)
        log.info("%-26s %8s %14s", "model", "ROC-AUC", "precision@10")
        log.info("%s", "-" * 52)
        for r in [baseline, *sorted(results, key=lambda r: -(r.auc if r.auc == r.auc else 0))]:
            log.info("%-26s %8.3f %14.3f", r.name, r.auc, r.precision_at_10)

    # Promotion is judged on the chronological split, which is the production question:
    # given what this person has done so far, what will they engage with next.
    run = run_training(
        user=args.user, test_frac=args.test_frac, mode="chronological",
        tune=args.tune, tune_iters=args.tune_iters, promote=args.promote,
        force=args.force, simulated=args.simulated,
    )
    if run.importances:
        log.info("\n%s: what it leaned on (chronological fit)", run.best)
        for feat, val in run.importances[:args.top_features]:
            log.info("   %-28s %+.4f", feat, val)

    log.info("\nGate: best is %s. %s", run.best, run.gate_reason)
    log.info("%s", run.message)
    if not run.saved:
        log.info("To try it anyway: --force, then request it with ranker=model.")


if __name__ == "__main__":
    main()
