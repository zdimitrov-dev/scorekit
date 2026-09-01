# scorekit

A visual discovery platform for piano music. Browse or search a board of cards, where
each card is a YouTube performance or tutorial, an IMSLP score, or a MuseScore listing,
and a like/save system learns your taste to personalise a home feed.

## The problem

Piano learners face a two-part gap that no single tool covers:

1. **What to play next** is unguided. There is no taste-based discovery by era, mood,
   difficulty or composer the way Spotify and Pinterest do it for their domains.
2. **Finding the sheet music** is fragmented across YouTube, IMSLP and MuseScore, with
   nothing connecting the three.

## Two feed modes

- **Search** queries a specific piece and returns a mixed board from all three sources.
  Pieces not yet in the corpus are ingested on demand and streamed in as they arrive.
- **Home** has no query. It ranks the corpus against what you have liked and saved.

## Status

All three source connectors are live. The corpus holds roughly 580 pieces seeded from
IMSLP's catalogue, each carrying derived tags (composer, era, form, instrumentation).
The feed UI is built, including live search, interaction logging and a content-based
recommender. A supervised model is wired into the feed behind a promotion gate: it only
serves once it beats the hand-tuned ranker on held-out data, which it cannot yet do on the
interaction log collected so far, so the content ranker is live.

## Architecture

- **Backend:** Python 3.13. Ingestion jobs per source, plus a FastAPI service the
  frontend calls for search, recommendations and interaction logging.
- **Storage:** Supabase (managed Postgres).
- **Frontend:** Next.js (App Router) with a masonry board.
- **Containerisation:** Docker.

### Pipeline

```
query
  -> each connector searches its source
  -> results normalised into Card objects
  -> YouTube results filtered to piano only
  -> attribution filter drops cards that are not the queried piece
  -> IMSLP enrichment (licence, instrumentation, style)
  -> upsert piece and cards into Supabase
  -> tags derived for the piece
  -> feed renders, interactions logged, recommender ranks Home
```

### Data model

| Table | Purpose |
|---|---|
| `pieces` | One row per real piece. Created the first time it is searched or seeded. |
| `cards` | One row per individual result (a video, a score, a listing), linked to a piece. This is what renders. |
| `piece_tags` | Derived features (composer, era, form, format, instrumentation) that the recommender ranks over. |
| `interactions` | Append-only log of impressions, opens, likes and saves. The recommender's training signal. |

Cards from different sources are never merged into one grouped result. Each stays its own
card; normalisation happens behind the scenes through a shared `piece_id` so preference
signal can be attributed across sources.

## Recommendation, and how it is evaluated

Home is ranked by tag affinity: a profile is built from what you have liked and saved,
weighted by signal strength and by how rare each tag is in the corpus, then every card is
scored against it and a diversity pass stops one composer filling the board. That ranker is
hand-tuned and it is what currently serves the feed.

Beside it sits a learned ranker. Four models are fitted and compared against the hand-tuned
one on identical rows: logistic regression, random forest, a random forest whose
hyperparameters are searched by cross-validation, and XGBoost. Features are crossed with
the user's history rather than one-hot per composer, so the model learns how much composer
matters relative to era instead of being told by hand-set weights.

### Evaluation

Two splits, answering different questions. **Chronological** splits each user's timeline
and trains on their past to predict their future, which is the production question.
**Cross-user** holds out whole people, which asks whether the model works for someone it
has never seen. Both are needed: a model can do well on the first by learning the specific
users it was given.

For every row, the user's taste profile is rebuilt from only what happened earlier than
that row. Without that the profile already contains the like being predicted, and the model
scores near-perfectly having learned nothing.

Measured on twelve simulated users, because a ranker cannot be judged before it has
traffic. Their preferences are written down as numbers, the model only ever sees the
behaviour those numbers produced, and the like rate is held near one in ten so an easy
class balance does not flatter the metrics.

| model | AUC, same users | AUC, held-out users |
|---|---|---|
| random forest (tuned) | **0.840** | 0.862 |
| random forest | 0.837 | **0.866** |
| logistic regression | 0.837 | 0.843 |
| xgboost | 0.823 | 0.836 |
| hand-tuned baseline | 0.823 | 0.844 |

AUC is the probability the model scores a liked piece above an unliked one. Random Forest
wins both modes, and beats XGBoost in both, which is why several models are fitted rather
than assuming boosting wins on tabular data.

### Did it recover the taste?

AUC is computed against behaviour, which is what the model was fitted on, so a high score
can come from learning the taste or from learning an artefact of collection. Simulated
users are the one case where that is separable: rank the whole corpus for each persona and
score the top ten against the preferences we wrote down. Scaled so 0% is a random ordering
and 100% is the best any ranking could achieve, mean over twelve personas:

| | recovered |
|---|---|
| learned model | **81%** |
| hand-tuned baseline | 79% |

Not uniform. The model takes `nordic-romantic` 100% to 42% and loses `bach-completist` 62%
to 100%, so it is a different set of strengths rather than a strict improvement.

### The gate

A fitted model is not automatically worth serving. On a small or skewed log it can rank
worse than the hand-tuned scoring, and shipping it would degrade the feed with nothing to
indicate why. A model serves only once it has at least 40 likes or saves to measure
against, beats chance, and beats the hand-tuned ranker by 0.03 AUC on held-out rows.

**Nothing has passed yet.** The best margin is +0.017 where +0.03 is required, so the feed
runs the hand-tuned ranker. The importances say why: the forest leans on `affinity_overall`,
`seen_composer_before` and `affinity_composer`, which is close to what the heuristic already
uses. What the model adds is learning the weight of each axis rather than being handed it,
and that is worth about two points of AUC.

### Two results that were wrong

A model scored 0.914 and passed the gate. It should not have. A client-side reconciliation
had written 42 likes with the same timestamp, so "earlier" stopped meaning anything and the
model saw 41 near-identical likes while predicting the 42nd. Events now carry the time they
happened rather than the time the row was written, and rows whose real time is unknown seed
the profile but are never scored against.

The first version of the recovery check scored 100% everywhere. Its definition of success
was "does the top ten contain any tag this persona wants", and a persona wanting `romantic`
matches 274 of 582 pieces, so nothing could fail it. It is still reported next to the real
measure, as a reminder that a metric everything passes measures nothing.

## Setup

```bash
python -m venv .venv && .venv/Scripts/activate     # Windows
pip install -r requirements.txt
cp .env.example .env                                # then fill in the keys
```

Frontend environment goes in `web/.env.local` (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`).

```bash
npm install          # root, for the dev launcher
npm run dev          # starts the API on :8000 and the web app on :3210
```

## Common commands

```bash
python -m scorekit.jobs.ingest --query "Clair de Lune"   # ingest one piece
python -m scorekit.jobs.seed --per-composer 15           # seed from IMSLP's catalogue
python -m scorekit.jobs.tag_pieces                       # rebuild piece_tags
python -m scorekit.jobs.stats                            # summarise the interaction log
python -m scorekit.jobs.train_model                      # train and evaluate the ranker
python -m scorekit.jobs.train_model --promote            # serve it if it clears the gate
python -m scorekit.jobs.train_model --force              # save a failing fit for testing
python -m scorekit.jobs.compare                          # heuristic vs model, side by side
python -m scorekit.jobs.simulate                         # synthetic users with a known taste
python -m scorekit.jobs.recover                          # did the model recover that taste?
python -m scorekit.jobs.migrate                          # apply db/migrations
pytest                                                    # run the test suite
```

## Sources

| Source | Access | Notes |
|---|---|---|
| YouTube | YouTube Data API | Structured and legal. Quota-limited to about 100 searches a day. Results are filtered to piano only. |
| IMSLP | MediaWiki API | Public-domain scores with rich metadata. No quota, so the corpus is seeded from here. |
| MuseScore | Tavily search restricted to musescore.com | Sidesteps blocked scraping and the discontinued MuseScore and Google Custom Search APIs. |

## Build phases

| Phase | Scope | State |
|---|---|---|
| 0 | Repo, Supabase schema, Docker skeleton | Done |
| 1 | YouTube connector | Done |
| 2 | IMSLP connector, enrichment, disambiguation | Done |
| 3 | MuseScore via Tavily | Done |
| 4 | Feed UI, live search, corpus seeding | Done |
| 5 | Interaction logging | Done |
| 6 | Recommendation engine | Content-based live; learned ranker gated on data volume |
| 7 | Polish and deploy | Not started |

See `PROJECT_CONTEXT.md` for design decisions and the reasoning behind them.
