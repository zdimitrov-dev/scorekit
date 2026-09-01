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
recommender. A supervised model is trained and evaluated offline but is not yet serving
the feed.

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
| 6 | Recommendation engine | Content-based live; learned ranker trained but not serving |
| 7 | Polish and deploy | Not started |

See `PROJECT_CONTEXT.md` for design decisions and the reasoning behind them.
