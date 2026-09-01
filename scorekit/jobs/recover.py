"""Did the model rediscover the taste we wrote down?

Every other measurement here is a metric computed against behaviour, and behaviour is what
the model was fitted on. A high AUC can come from learning the taste or from learning some
artefact of how the data was collected, and the number looks the same either way. The
0.914 that turned out to be fabricated timestamps scored better than anything honest has.

Simulated personas are the one case where that ambiguity is escapable. Their preferences
are written down in ``simulate.PERSONAS`` as numbers, the model never sees those numbers,
and it only ever sees the behaviour they produced. So the corpus can be ranked for a
persona and the top of that ranking checked against the answer key.

Reported against two references, because a bare number means nothing on its own:

``heuristic``  the hand-tuned scoring, which is what the model has to beat to be worth
               serving at all.
``random``     the share of the corpus that matches this persona anyway. Ranking Chopin
               first is unimpressive if a third of the corpus is Chopin.

    python -m scorekit.jobs.recover
    python -m scorekit.jobs.recover --top 20 --persona chopin-devotee
"""
from __future__ import annotations

import argparse
import logging
import uuid
from typing import Any

from ..ml.features import build_profile, corpus_weights, features_for
from ..ml.pipeline import load_training_data
from ..ml.registry import load_model
from ..recommend import SIGNAL_WEIGHTS, affinity
from ..recommend import build_profile as heuristic_profile
from .simulate import _NS, PERSONAS

log = logging.getLogger("scorekit.recover")


def _persona_score(tags: list[tuple[str, str]], persona: dict[tuple[str, str], float]) -> float:
    """How much this persona actually wants the piece, by the written-down weights."""
    return sum(persona.get(t, 0.0) for t in tags)


def _hit(tags: list[tuple[str, str]], persona: dict[tuple[str, str], float]) -> bool:
    """Carries at least one tag the persona was written to want.

    Kept only as a floor. It saturates: every ranker scores 100%, because a persona that
    wants "romantic" matches 274 of 582 pieces and any competent ranking fills its top ten
    with them. A metric nothing can fail cannot tell two rankers apart.
    """
    return any(persona.get(t, 0.0) > 0 for t in tags)


def _recovered(top_scores: list[float], ideal: float, corpus_mean: float) -> float:
    """How much of the achievable taste the ranking actually captured, 0 to 1.

    The raw mean is unreadable on its own, because personas differ in how much of the
    corpus they like at all. Scaling between what a random pick would get and the best any
    ranking could get makes the personas comparable: 0 is no better than chance, 1 is the
    optimal ordering.
    """
    got = sum(top_scores) / len(top_scores)
    span = ideal - corpus_mean
    return 0.0 if span <= 0 else max(0.0, (got - corpus_mean) / span)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the model recovered a known taste.")
    parser.add_argument("--top", type=int, default=10, help="how far down the ranking to look")
    parser.add_argument("--persona", help="just this one")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    loaded = load_model()
    if loaded is None:
        raise SystemExit("No saved model. Run: python -m scorekit.jobs.train_model "
                         "--simulated only --force")
    log.info("model: %s (promoted=%s)\n", loaded.meta.get("name"), loaded.promoted)

    events, cards, tags, _ = load_training_data(simulated="only")
    if not events:
        raise SystemExit("No simulated history. Run: python -m scorekit.jobs.simulate")
    card_list = list(cards.values())
    weights = corpus_weights(tags)

    by_user: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        by_user.setdefault(e["user_id"], []).append(e)
    # Which persona each user id belongs to, derived the same way simulate derives it.
    name_of = {str(uuid.uuid5(_NS, name)): name for name in PERSONAS}

    log.info("How much of the achievable taste each ranking captured in its top %d.",
             args.top)
    log.info("0% is a random ordering; 100% is the best any ranking could do.")
    log.info("")
    log.info("%-24s %8s %11s %10s %11s", "persona", "model", "heuristic",
             "any-tag hit", "likes/saves")
    log.info("%s", "-" * 70)

    totals = {"model": 0.0, "heuristic": 0.0, "hit": 0.0}
    counted = 0
    for user_id, user_events in sorted(by_user.items(), key=lambda kv: name_of.get(kv[0], "")):
        name = name_of.get(user_id)
        if not name or (args.persona and name != args.persona):
            continue
        persona = PERSONAS[name]

        positives = [(e.get("piece_id"), SIGNAL_WEIGHTS.get(e["action"], 0.0))
                     for e in user_events if e["action"] in ("like", "save")]
        positives = [(p, w) for p, w in positives if p]
        if not positives:
            continue

        # The model's ranking. Its profile comes from behaviour only; the persona weights
        # are never handed to it.
        import numpy as np
        profile = build_profile(positives, tags, weights)
        rows = np.asarray([features_for(c, tags, profile, weights) for c in card_list],
                          dtype=float)
        scores = loaded.model.predict_proba(rows)[:, 1]
        order = np.argsort(-scores)[:args.top]

        # The hand-tuned ranking over the same cards, for reference.
        h_profile = heuristic_profile([(p, "like") for p, _ in positives], tags)
        h_scores = [affinity(tags.get(c["piece_id"], []), h_profile, weights) for c in card_list]
        h_order = sorted(range(len(card_list)), key=lambda i: -h_scores[i])[:args.top]

        # The answer key: what the persona actually wants, by the written-down weights.
        truth = [_persona_score(tags.get(c["piece_id"], []), persona) for c in card_list]
        corpus_mean = sum(truth) / len(truth)
        ideal = sum(sorted(truth, reverse=True)[:args.top]) / args.top

        m = _recovered([truth[i] for i in order], ideal, corpus_mean)
        h = _recovered([truth[i] for i in h_order], ideal, corpus_mean)
        hit = sum(_hit(tags.get(card_list[i]["piece_id"], []), persona)
                  for i in order) / args.top

        totals["model"] += m
        totals["heuristic"] += h
        totals["hit"] += hit
        counted += 1
        log.info("%-24s %7.0f%% %10.0f%% %9.0f%% %11d",
                 name, m * 100, h * 100, hit * 100, len(positives))

    if counted:
        log.info("%s", "-" * 70)
        log.info("%-24s %7.0f%% %10.0f%% %9.0f%%   mean over %d personas", "",
                 totals["model"] / counted * 100, totals["heuristic"] / counted * 100,
                 totals["hit"] / counted * 100, counted)


if __name__ == "__main__":
    main()
