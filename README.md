# scorekit

A Pinterest-style discovery platform for piano music. Browse or search a feed of
cards — each a YouTube tutorial/cover, an IMSLP score, or a MuseScore listing —
and a swipe-based like/skip system learns your taste to personalize a home feed.

Two feed modes over one system:

- **Search feed** — query a piece, get a mixed board of every card type found
  across all sources.
- **Home feed** — no query; a personalized, ranked feed built from accumulated
  like/skip signal (diverse default for new users).

## Status

**Phase 1 — YouTube connector live.** Supabase schema is applied (RLS on),
ingestion persists pieces + cards, and the YouTube connector searches, enriches,
and upserts results end-to-end. IMSLP/MuseScore connectors and the feed are next.
See the build plan below.

## Architecture

- **Backend**: Python, scheduled ingestion jobs per source
- **Storage**: Supabase (Postgres)
- **Containerization**: Docker
- **Frontend** (later): Pinterest-style masonry feed, swipe like/skip

### Data model

| Table | Purpose |
|---|---|
| `pieces` | Canonical entity per real piece (normalized title, composer, era, difficulty). Created the first time a piece is searched or ingested. |
| `cards` | One row per individual result (a specific video, score, or link), FK to `piece_id`. This is what renders in the feed. |
| `interactions` | `user_id`, `card_id`/`piece_id`, `action` (like/skip/click), `dwell_ms`, `feed_position`, timestamp. The recommender's training signal. `skip` is the negative (no explicit dislike, TikTok-style); `dwell_ms` is the engagement-intensity weight layered on top of the action; `feed_position` is stored for later position-bias correction. |
| `piece_tags` | composer, era, mood, difficulty and other features the recommender learns over. |

Cards from different sources are **never merged** into a single grouped result —
each is its own card in a mixed feed. Normalization happens quietly behind the
scenes via a shared `piece_id` so the preference-learning layer can attribute
signal correctly across sources.

## Getting started

```bash
# 1. Create and fill your env file
cp .env.example .env

# 2. Apply the database schema to your Supabase project
#    (Supabase SQL editor, or psql against the connection string)
psql "$SUPABASE_DB_URL" -f db/schema.sql

# 3. Install and run locally
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m scorekit.jobs.ingest --query "Clair de Lune"
```

Or with Docker:

```bash
docker compose run --rm ingest --query "Clair de Lune"
```

## Build plan

| Phase | Scope |
|---|---|
| 0 | Repo, Supabase schema (live, RLS on), Docker skeleton ✅ |
| 1 | YouTube connector — search, enrich, persist ✅ |
| 2 | IMSLP connector — framework laid (gated pending terms) |
| 3 | MuseScore via Google Custom Search |
| 4 | Search feed UI (mixed-card masonry) |
| 5 | Swipe interaction + logging |
| 6 | Recommendation engine (home feed) — the ML centerpiece |
| 7 | Polish + deploy |

## Data sources

| Source | Access | Notes |
|---|---|---|
| YouTube | YouTube Data API | Legal, structured. Descriptions often contain sheet-music links. |
| IMSLP | Direct access | Public-domain classical scores. Confirm current terms before Phase 2. |
| MuseScore | Google Custom Search (`site:musescore.com`), cached per piece | Sidesteps blocked scraping; only links out to already-indexed results. |
