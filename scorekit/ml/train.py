"""Train and compare candidate rankers.

Three models are fitted, not one, because at a few hundred rows **which one wins is an
empirical question** and assuming the fanciest is best is how people ship worse models:

``logistic``  The baseline, and a serious contender. Linear, so it cannot express "romantic
              AND nocturne", but at small *n* that limitation is also protection — there is
              far less to overfit. Its coefficients are directly comparable to the
              hand-tuned ``recommend.KEY_WEIGHTS``, which is the comparison this project
              exists to make. Any model that cannot beat it is not earning its complexity.

``forest``    Random Forest — many deep trees on bootstrapped samples, averaged. Each tree
              overfits happily; averaging decorrelated trees cancels most of it, so it is
              hard to get badly wrong and needs almost no tuning. It usually trails boosting
              on tabular data because every tree fits the same target independently rather
              than correcting the previous one's mistakes.

``xgboost``   Gradient boosting — trees fitted **in sequence**, each one on what the
              ensemble still gets wrong. Typically the strongest on tabular data, and the
              only one of the three that reads NaN as a branch rather than needing it filled
              in, which matters here because a missing view count is a real fact about the
              source. The cost is that it will happily memorise a small dataset, so it is
              the most heavily regularised of the three.

**Evaluation is ranking-first.** Accuracy is meaningless on a feed: with likes rare, a model
that predicts "no" every time scores ~95%. What matters is whether the things a user
engaged with are pushed to the *top*, so the headline metrics are ROC-AUC (probability a
random positive outranks a random negative) and precision@10 (how much of a screenful is
worth looking at). Both are compared against the existing heuristic on the same rows.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

from .dataset import Dataset

log = logging.getLogger("scorekit.ml.train")


@dataclass
class Result:
    name: str
    auc: float
    precision_at_10: float
    n_train: int
    n_test: int
    model: Any = None
    importances: list[tuple[str, float]] | None = None


def _split_indices(data: Dataset, test_frac: float, mode: str) -> tuple[list[int], list[int]]:
    """Which rows train and which are held out.

    ``chronological`` — split **each user's** history independently, training on their past
    and testing on their future. This is the production question: given what this person has
    done so far, what will they engage with next.

    Splitting the pooled rows instead is a trap, and it caught me: rows are grouped by user,
    so a single 70/30 cut put every test row inside one user and silently measured something
    else entirely.

    ``cross_user`` — hold out whole users. A much harder question — can the model rank for
    somebody whose history it has never seen — and the one that says whether the
    history-crossed features generalise or whether it has just memorised three people.
    """
    by_user: dict[str, list[int]] = {}
    for i, user in enumerate(data.groups):
        by_user.setdefault(user, []).append(i)

    train: list[int] = []
    test: list[int] = []
    if mode == "cross_user":
        users = sorted(by_user)
        held = set(users[-max(1, int(len(users) * test_frac)):])
        for user, idxs in by_user.items():
            (test if user in held else train).extend(idxs)
    else:
        for idxs in by_user.values():
            cut = max(1, int(len(idxs) * (1 - test_frac)))
            train.extend(idxs[:cut])
            test.extend(idxs[cut:])
    return train, test


def _split_chronological(data: Dataset, test_frac: float = 0.3, mode: str = "chronological"):
    train, test = _split_indices(data, test_frac, mode)
    X = np.asarray(data.X, dtype=float)
    y = np.asarray(data.y, dtype=int)
    w = np.asarray(data.weight, dtype=float)
    return X[train], y[train], w[train], X[test], y[test]


def _precision_at_k(y_true: np.ndarray, scores: np.ndarray, k: int = 10) -> float:
    if len(y_true) == 0:
        return 0.0
    k = min(k, len(y_true))
    top = np.argsort(-scores)[:k]
    return float(y_true[top].sum() / k)


def _auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    if len(set(y_true.tolist())) < 2:
        return float("nan")     # undefined with only one class present
    return float(roc_auc_score(y_true, scores))


def _build_models(pos_weight: float) -> dict[str, Any]:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBClassifier

    return {
        # Neither of the first two understands NaN, so missing values are imputed to the
        # column median; only XGBoost gets to treat "missing" as information.
        "logistic": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),            # coefficients only comparable on a common scale
            LogisticRegression(
                max_iter=2000,
                C=1.0,                   # inverse regularisation; 1.0 is a firm default
                class_weight="balanced", # counteract likes being far rarer than impressions
            ),
        ),
        "forest": make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(
                n_estimators=400,        # more trees only ever reduces variance; cheap here
                max_depth=6,             # the main brake on memorising a small dataset
                min_samples_leaf=5,      # no leaf may rest on one or two examples
                max_features="sqrt",     # decorrelates the trees, which is what makes
                                         # averaging work
                class_weight="balanced_subsample",
                random_state=0,
                n_jobs=-1,
            ),
        ),
        "xgboost": XGBClassifier(
            n_estimators=300,
            learning_rate=0.05,          # small steps: more trees each correcting a little
                                         # generalises better than few aggressive ones
            max_depth=3,                 # shallow on purpose — depth 3 still expresses
                                         # three-way interactions, deeper just memorises
            min_child_weight=3.0,        # a split must keep this much weight on both sides
            subsample=0.8,               # each tree sees 80% of rows ...
            colsample_bytree=0.8,        # ... and 80% of features: bagging inside boosting
            reg_lambda=2.0,              # L2 on leaf values, shrinking confident leaves
            reg_alpha=0.0,               # L1; left off, no reason to force sparsity here
            gamma=0.0,                   # min gain to split; depth already constrains us
            scale_pos_weight=pos_weight, # the class-imbalance lever
            eval_metric="logloss",
            random_state=0,
            n_jobs=-1,
        ),
    }


def _importances(name: str, model: Any, feature_names: list[str]) -> list[tuple[str, float]]:
    """What the model actually leaned on.

    For logistic regression these are signed coefficients — the sign says whether a feature
    pushes toward or away from a like, which the tree importances cannot tell you.
    """
    est = model[-1] if hasattr(model, "__getitem__") and hasattr(model, "steps") else model
    if hasattr(est, "coef_"):
        vals = est.coef_[0]
    elif hasattr(est, "feature_importances_"):
        vals = est.feature_importances_
    else:
        return []
    return sorted(zip(feature_names, (float(v) for v in vals)),
                  key=lambda kv: -abs(kv[1]))


def train_all(data: Dataset, test_frac: float = 0.3,
              mode: str = "chronological") -> list[Result]:
    X_tr, y_tr, w_tr, X_te, y_te = _split_chronological(data, test_frac, mode)
    if y_tr.sum() == 0:
        raise ValueError(
            "no positive examples in the training split — a classifier cannot be fitted. "
            "Browse the feed and like some pieces, or run scorekit.jobs.simulate."
        )

    neg, pos = int((y_tr == 0).sum()), int(y_tr.sum())
    pos_weight = (neg / pos) if pos else 1.0
    log.info("train=%d (%d positive) test=%d | scale_pos_weight=%.2f",
             len(y_tr), pos, len(y_te), pos_weight)

    results: list[Result] = []
    for name, model in _build_models(pos_weight).items():
        try:
            model.fit(X_tr, y_tr, **({} if name != "logistic" else {}))
        except Exception as exc:
            log.warning("%s failed to fit: %s", name, exc)
            continue
        scores = model.predict_proba(X_te)[:, 1] if len(X_te) else np.array([])
        results.append(Result(
            name=name,
            auc=_auc(y_te, scores) if len(X_te) else float("nan"),
            precision_at_10=_precision_at_k(y_te, scores) if len(X_te) else float("nan"),
            n_train=len(y_tr), n_test=len(y_te), model=model,
            importances=_importances(name, model, data.feature_names),
        ))
    return results


def heuristic_baseline(data: Dataset, test_frac: float = 0.3,
                       mode: str = "chronological") -> Result:
    """The existing hand-tuned ranker, scored on the same held-out rows.

    ``affinity_overall`` *is* the heuristic's judgement, so ranking the test set by that one
    column reproduces what ``recommend.py`` would have done — and any learned model has to
    beat it to justify existing.
    """
    _X_tr, _y_tr, _w, X_te, y_te = _split_chronological(data, test_frac, mode)
    col = data.feature_names.index("affinity_overall")
    scores = X_te[:, col] if len(X_te) else np.array([])
    return Result(
        name="heuristic (tag affinity)",
        auc=_auc(y_te, scores) if len(X_te) else float("nan"),
        precision_at_10=_precision_at_k(y_te, scores) if len(X_te) else float("nan"),
        n_train=0, n_test=len(y_te),
    )
