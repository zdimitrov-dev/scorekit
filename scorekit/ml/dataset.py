"""Building a training set out of the interaction log.

Two decisions here matter more than any model choice.

**What counts as a positive.** ``like`` and ``save`` are explicit, but rare — most people
never press either. A long ``click`` (the card was opened and held open) is the strongest
*behavioural* signal the feed produces and is far more common, so it counts too. An
``impression`` — seen and passed over — is the negative, which is the only reason negatives
exist at all: the feed has no reject control.

**Leakage.** A user's profile must be built only from engagements the model is allowed to
have seen. Building it from everything and then predicting a held-out like means the
profile already contains that like's tags, and the model scores ~perfectly while having
learned nothing. Splitting is therefore **chronological**: the profile comes from the past,
the evaluation from the future — which is also how it would run in production.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from .features import FEATURE_NAMES, build_profile, features_for

# A click held this long is treated as a positive on its own.
LONG_CLICK_MS = 8000
# How much each signal contributes to the taste profile (mirrors recommend.SIGNAL_WEIGHTS).
POSITIVE_WEIGHT = {"save": 1.5, "like": 1.0, "click": 0.6}


def is_positive(event: dict[str, Any]) -> bool:
    action = event.get("action")
    if action in ("like", "save"):
        return True
    if action == "click":
        return (event.get("dwell_ms") or 0) >= LONG_CLICK_MS
    return False


def is_negative(event: dict[str, Any]) -> bool:
    """Seen and not engaged with. A short click counts too — opened, and abandoned."""
    if event.get("action") == "impression":
        return True
    return event.get("action") == "click" and (event.get("dwell_ms") or 0) < LONG_CLICK_MS


@dataclass
class Dataset:
    X: list[list[float]] = field(default_factory=list)
    y: list[int] = field(default_factory=list)
    weight: list[float] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)   # user id per row
    feature_names: list[str] = field(default_factory=lambda: list(FEATURE_NAMES))

    def __len__(self) -> int:
        return len(self.y)

    @property
    def positives(self) -> int:
        return sum(self.y)


def build_dataset(
    events: Iterable[dict[str, Any]],
    cards: dict[str, dict[str, Any]],
    piece_tags: dict[str, list[tuple[str, str]]],
    weights: dict[tuple[str, str], float],
    warmup: float = 0.4,
) -> Dataset:
    """Rows from a user's chronologically ordered events.

    ``warmup`` is the fraction of each user's history used only to seed their profile and
    never emitted as training rows. Without it the earliest rows are scored against an
    empty profile, where every affinity feature is 0 and the label looks like noise.
    """
    by_user: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        by_user.setdefault(e["user_id"], []).append(e)

    data = Dataset()
    for user_id, user_events in by_user.items():
        user_events.sort(key=lambda e: (e.get("created_at") or "", e.get("id") or 0))
        split = int(len(user_events) * warmup)

        positives: list[tuple[str, float]] = []
        for i, event in enumerate(user_events):
            card = cards.get(event.get("card_id") or "")
            piece_id = event.get("piece_id") or (card or {}).get("piece_id")

            # The profile is always built from *earlier* events only, so a row is never
            # scored against a profile that already contains its own label.
            if i >= split and card is not None and piece_id:
                profile = build_profile(positives, piece_tags, weights)
                if is_positive(event) or is_negative(event):
                    data.X.append(features_for(card, piece_tags, profile, weights))
                    data.y.append(1 if is_positive(event) else 0)
                    data.weight.append(_row_weight(event))
                    data.groups.append(user_id)

            if is_positive(event) and piece_id:
                positives.append((piece_id, POSITIVE_WEIGHT.get(event["action"], 1.0)))

    return data


def _row_weight(event: dict[str, Any]) -> float:
    """Confidence in the label.

    A card glanced at for a second is weak evidence of dislike; one held for half a minute
    and still not liked is strong. Dwell weights the *example* rather than being a feature,
    because it is only observable after the card is shown and would not exist at scoring
    time — using it as a feature would be leakage.
    """
    if is_positive(event):
        return POSITIVE_WEIGHT.get(event.get("action", ""), 1.0)
    dwell = event.get("dwell_ms") or 0
    return 1.0 if dwell >= 4000 else 0.6


def label_summary(data: Dataset) -> str:
    pos, total = data.positives, len(data)
    ratio = f"1:{(total - pos) / pos:.1f}" if pos else "no positives"
    return f"{total} rows, {pos} positive, {total - pos} negative (ratio {ratio})"


def group_counts(data: Dataset) -> Counter[str]:
    return Counter(data.groups)
