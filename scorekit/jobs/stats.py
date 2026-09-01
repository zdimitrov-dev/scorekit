"""A readable summary of the interaction log.

Browsing the raw table is misleading: impressions outnumber likes by roughly 30 to 1 and
are interleaved with them, so the first screen of rows is *always* impressions and it looks
as though nothing else is being recorded.

    python -m scorekit.jobs.stats
    python -m scorekit.jobs.stats --recent 20
"""
from __future__ import annotations

import argparse
from collections import Counter

from ..db import get_client


def _page(sb, table: str, select: str) -> list[dict]:
    out: list[dict] = []
    while True:
        rows = sb.table(table).select(select).range(len(out), len(out) + 999).execute().data or []
        out += rows
        if len(rows) < 1000:
            return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise the interaction log.")
    parser.add_argument("--recent", type=int, default=10, help="show this many latest events")
    args = parser.parse_args()

    sb = get_client()
    rows = _page(sb, "interactions", "id,user_id,action,card_id,dwell_ms,created_at")
    if not rows:
        print("No interactions logged yet.")
        return
    rows.sort(key=lambda r: r["id"])
    cards = {c["id"]: c for c in _page(sb, "cards", "id,title,author")}
    counts = Counter(r["action"] for r in rows)

    print(f"{len(rows)} interactions from {len({r['user_id'] for r in rows})} viewer(s)\n")
    for action in ("like", "save", "click", "impression", "skip"):
        n = counts.get(action, 0)
        if not n:
            continue
        share = 100 * n / len(rows)
        label = {
            "like": "liked", "save": "saved", "click": "opened a card",
            "impression": "scrolled past", "skip": "skipped",
        }[action]
        print(f"  {label:16} {n:>5}  ({share:4.1f}%)")

    positives = counts.get("like", 0) + counts.get("save", 0)
    negatives = counts.get("impression", 0) + counts.get("skip", 0)
    print(f"\n  positives vs negatives: {positives} : {negatives}")
    if positives < 30:
        print(f"  -> {30 - positives} more likes/saves before training means much")

    print(f"\nMost recent {args.recent} engagements (likes, saves and opens):")
    engaged = [r for r in rows if r["action"] in ("like", "save", "click")][-args.recent:]
    for r in reversed(engaged):
        card = cards.get(r["card_id"] or "", {})
        dwell = f"{r['dwell_ms'] / 1000:.0f}s" if r.get("dwell_ms") else ""
        title = (card.get("title") or "?")[:46]
        print(f"  {r['action']:<6} {dwell:>5}  {title}")


if __name__ == "__main__":
    main()
