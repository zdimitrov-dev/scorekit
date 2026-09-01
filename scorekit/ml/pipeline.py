"""One training run, callable from anywhere.

The CLI (`jobs.train_model`) and the dev dashboard's retrain button both go through here,
so there is one definition of what "retrain" means rather than two that drift apart.

Training is a batch job over the whole interaction log, not a per-request operation: it
reads every event, fits three or four models and scores them on held-out rows. That takes a
few seconds untuned and around forty with a hyperparameter search, which is why it is
triggered rather than run inline on a like.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from ..db import get_client
from .dataset import build_dataset, label_summary
from .features import corpus_weights
from .registry import gate, save_model
from .train import heuristic_baseline, train_all, tune_forest

log = logging.getLogger("scorekit.ml.pipeline")

# backfilled is added by migration 002 and may not exist yet, so it is requested
# separately and the query falls back without it.
_BASE_COLUMNS = "id,user_id,action,card_id,piece_id,dwell_ms,feed_position,created_at"
_EVENT_COLUMNS = _BASE_COLUMNS + ",backfilled"


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


def load_training_data(user: str | None = None, simulated: str = "exclude"):
    """Everything a fit needs, plus how many rows the simulated filter removed.

    ``simulated`` is "exclude" by default so a taste invented by ``jobs.simulate`` can never
    count toward the promotion gate. The dropped count is returned because "no positive
    examples" is a confusing thing to be told while the log visibly holds thousands of
    likes, and the difference between the two is entirely this filter.
    """
    from ..jobs.simulate import simulated_user_ids

    sb = get_client()
    kw = {"user_id": user} if user else {}
    try:
        events = _page(sb, "interactions", _EVENT_COLUMNS, **kw)
    except Exception:
        # Migration 002 has not been applied. Everything still works; reconciled likes are
        # simply indistinguishable from logged ones until it is.
        log.warning("interactions.backfilled is missing; apply db/migrations/002 so "
                    "reconciled likes are not read as chronology")
        events = _page(sb, "interactions", _BASE_COLUMNS, **kw)
    cards = {c["id"]: c for c in _page(sb, "cards", "id,piece_id,source,kind,metadata")}
    tags: dict[str, list[tuple[str, str]]] = {}
    for t in _page(sb, "piece_tags", "piece_id,key,value"):
        tags.setdefault(t["piece_id"], []).append((t["key"], t["value"]))

    sim = simulated_user_ids()
    before = len(events)
    if simulated == "exclude":
        events = [e for e in events if e["user_id"] not in sim]
    elif simulated == "only":
        events = [e for e in events if e["user_id"] in sim]
    return events, cards, tags, before - len(events)


@dataclass
class TrainingRun:
    """What one run produced. Plain data, so it survives being sent to a browser."""
    ok: bool = False
    message: str = ""
    dataset: str = ""
    positives: int = 0
    rows: int = 0
    promoted: bool = False
    saved: bool = False
    best: str = ""
    gate_reason: str = ""
    heuristic_auc: float = float("nan")
    excluded_simulated: int = 0
    scores: list[dict[str, Any]] = field(default_factory=list)
    importances: list[tuple[str, float]] = field(default_factory=list)


def run_training(
    user: str | None = None,
    test_frac: float = 0.3,
    mode: str = "chronological",
    tune: bool = False,
    tune_iters: int = 40,
    promote: bool = False,
    force: bool = False,
    simulated: str = "exclude",
) -> TrainingRun:
    """Fit the candidates, judge them against the heuristic, and save if asked.

    ``promote`` saves only when the gate passes; ``force`` saves regardless, marked as not
    promoted so the feed will not use it unless a request names it.
    """
    events, cards, tags, dropped = load_training_data(user, simulated)
    data = build_dataset(events, cards, tags, corpus_weights(tags))
    run = TrainingRun(dataset=label_summary(data), positives=data.positives,
                      rows=len(data), excluded_simulated=dropped)
    if data.positives == 0:
        run.message = (
            f"No positive examples. {dropped} simulated rows were excluded, which is the "
            "default so an invented taste cannot promote a model; train on them "
            "deliberately, or like some pieces in the feed."
            if dropped else
            "No positive examples yet. Like something in the feed, or run "
            "scorekit.jobs.simulate for a synthetic taste."
        )
        return run

    results = train_all(data, test_frac, mode)
    if tune:
        tuned = tune_forest(data, test_frac, mode, tune_iters)
        if tuned is not None:
            results.append(tuned)
    baseline = heuristic_baseline(data, test_frac, mode)

    run.ok = True
    run.heuristic_auc = baseline.auc
    run.scores = [{"name": r.name, "auc": r.auc, "precision_at_10": r.precision_at_10}
                  for r in sorted(results, key=lambda r: -(r.auc if r.auc == r.auc else 0))]

    best = max(results, key=lambda r: r.auc if r.auc == r.auc else -1)
    ok, reason = gate(best.auc, baseline.auc, data.positives)
    run.best, run.promoted, run.gate_reason = best.name, ok, reason
    run.importances = (best.importances or [])[:10]

    if not (promote or force):
        run.message = ("Passes the gate; re-run with promote to serve it." if ok
                       else f"Not promoted. {reason}")
        return run
    if not ok and not force:
        run.message = f"Not promoted. {reason} The feed keeps using the content ranker."
        return run

    save_model(best.model, data.feature_names, {
        "name": best.name,
        "passed_gate": ok,
        "gate_reason": reason,
        "auc": best.auc,
        "heuristic_auc": baseline.auc,
        "precision_at_10": best.precision_at_10,
        "n_train": best.n_train,
        "n_test": best.n_test,
        "positives": data.positives,
        "feature_names": data.feature_names,
    })
    run.saved = True
    run.message = (f"Promoted {best.name}. The feed will use it." if ok
                   else f"Saved {best.name} for testing only. {reason}")
    return run


# --- background execution ---------------------------------------------------
#
# A tuned run takes around forty seconds, far too long to hold an HTTP request open. The
# dashboard therefore starts a run and polls this state. One run at a time: training is
# CPU-bound across every core already, and two at once would only make both slower.

_lock = threading.Lock()
_state: dict[str, Any] = {"running": False, "started_at": None, "result": None, "error": None}


def training_state() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def start_training(**kwargs: Any) -> bool:
    """Kick off a run in the background. False if one is already going."""
    import time

    with _lock:
        if _state["running"]:
            return False
        _state.update(running=True, started_at=time.time(), result=None, error=None)

    def worker() -> None:
        try:
            result = run_training(**kwargs)
            with _lock:
                _state.update(running=False, result=result, error=None)
        except Exception as exc:
            log.exception("training failed")
            with _lock:
                _state.update(running=False, result=None, error=str(exc))

    threading.Thread(target=worker, daemon=True).start()
    return True
