"""Where a trained ranker is kept, and the gate it must pass to be used.

The gate is the point of this module. A model that has been fitted is not automatically a
model worth serving: on a small or skewed interaction log it can rank worse than the
hand-tuned heuristic, and worse than chance. Promoting it anyway would quietly degrade the
feed with nothing to indicate why, so a fit is only saved when it beats the heuristic on
held-out rows by a real margin, on enough positives for the comparison to mean anything.

Until that happens the feed keeps using the content ranker, which is the correct outcome
rather than a failure.

A fit that fails the gate can still be **saved for testing**, marked as not promoted. It is
never used automatically, but a caller can ask for it by name, so the model can be tried
side by side with the heuristic before it has earned the feed.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("scorekit.ml.registry")

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
MODEL_PATH = MODEL_DIR / "ranker.joblib"
META_PATH = MODEL_DIR / "ranker.json"

# Below this many positive examples, a held-out score is noise: a handful of likes in the
# test split makes AUC swing wildly on one row landing differently.
MIN_POSITIVES = 40
# The model has to be better than the heuristic by more than measurement wobble, not merely
# ahead of it.
MIN_AUC_GAIN = 0.03


@dataclass
class LoadedModel:
    model: Any
    feature_names: list[str]
    meta: dict[str, Any]

    @property
    def promoted(self) -> bool:
        """Whether it passed the gate. Unpromoted models exist only for testing."""
        return bool(self.meta.get("passed_gate"))


def gate(auc: float, heuristic_auc: float, positives: int) -> tuple[bool, str]:
    """Should this fit be promoted? Returns (ok, reason)."""
    if positives < MIN_POSITIVES:
        return False, (f"only {positives} positive examples, need {MIN_POSITIVES} "
                       "before a held-out score means anything")
    if auc != auc:  # NaN, which happens when a split holds only one class
        return False, "could not be scored (held-out rows are all one class)"
    if auc <= 0.5:
        return False, f"AUC {auc:.3f} is no better than chance"
    if auc < heuristic_auc + MIN_AUC_GAIN:
        return False, (f"AUC {auc:.3f} does not beat the heuristic ({heuristic_auc:.3f}) "
                       f"by the required {MIN_AUC_GAIN}")
    return True, f"AUC {auc:.3f} vs heuristic {heuristic_auc:.3f}"


def save_model(model: Any, feature_names: list[str], meta: dict[str, Any]) -> Path:
    import joblib

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return MODEL_PATH


_cache: LoadedModel | None = None
_loaded = False


def load_model(refresh: bool = False) -> LoadedModel | None:
    """The promoted model, or None when none has passed the gate.

    Cached, because the feed asks on every request and unpickling is not free.
    """
    global _cache, _loaded
    if _loaded and not refresh:
        return _cache
    _loaded = True
    _cache = None
    if not (MODEL_PATH.exists() and META_PATH.exists()):
        return None
    try:
        import joblib

        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        _cache = LoadedModel(joblib.load(MODEL_PATH), meta.get("feature_names", []), meta)
    except Exception:
        # A model that cannot be loaded must not take the feed down with it.
        log.exception("failed to load the ranker; falling back to the content ranker")
        _cache = None
    return _cache


def model_info() -> dict[str, Any]:
    """What is on disk, and whether the feed will use it on its own."""
    loaded = load_model()
    if loaded is None:
        return {"available": False, "promoted": False}
    return {
        "available": True,
        "promoted": loaded.promoted,
        **{k: v for k, v in loaded.meta.items() if k != "feature_names"},
    }
