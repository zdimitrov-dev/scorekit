# Development surface

Everything here exists to make the recommender testable and must be removed before
release. It is unauthenticated and destructive by design, which is only acceptable while
the app runs on localhost.

None of it is reachable from the product UI: `/dev` is not linked from the navigation, and
no dev control renders on the feed. Visit it directly.

## What `/dev` gives you

| Panel | What it is for |
|---|---|
| Which ranker is live | Whether the feed is served by the trained model or the hand-tuned scoring, plus a three-way override: auto, force model, force content |
| Model scores | The saved fit's held-out AUC against the heuristic, and the gate it did or did not pass |
| Corpus | Piece, card and tag counts by source |
| Interactions | The training log by action, how far it is from the promotion threshold, and what this browser holds |

Two retrain buttons run a fit on the server, tuned or not. Three reset controls clear
impressions, the whole interaction log, or this browser and its rows together. Each
destructive control takes two presses and names what it is about to delete.

## Removing it

Delete these, and nothing else references them:

```
web/app/dev/                     the page
web/app/api/dev/                 its proxies
web/components/DevDashboard.tsx  the dashboard
DEV_SURFACE.md                   this file
```

Then remove from `scorekit/api.py`: `GET /dev/stats`, `POST /dev/clear-interactions`,
`POST /dev/train`, `GET /dev/train`, and the `ClearInteractionsRequest` and `TrainRequest`
models. `RecommendRequest.ranker` can stay: "auto" is the product behaviour and the
override is only ever set from the dashboard.

`scorekit/ml/pipeline.py` stays. The CLI uses it too, and it is where a scheduled retrain
would hook in.
