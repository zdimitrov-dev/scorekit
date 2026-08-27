# scorekit — Project Context

> **Start here.** This is the primary context document for scorekit — the design,
> current state, and roadmap in one place. Keep it in sync with the code as the
> project evolves (see [Keeping this file current](#keeping-this-file-current)).

**Last updated:** 2026-08-27 · **Phase:** Supabase live; Phase 1 (YouTube) in progress ·
**Repo:** https://github.com/zdimitrov-dev/scorekit

---

## 1. Status at a glance

| Area | State |
|---|---|
| Repo scaffold (Phase 0) | ✅ Done, committed, pushed to `main` |
| Database schema (`db/schema.sql`) | ✅ Applied to live Supabase; RLS enabled on all tables |
| Supabase project | ✅ Provisioned — schema applied, RLS on, `.env` filled & connection verified |
| Docker image build | ⛔ Not built/verified yet |
| Source connectors | 🟡 YouTube built + unit-tested (needs API key); IMSLP/MuseScore still stubs |
| Persistence (ingest → Supabase) | ✅ Built & verified live (`scorekit/store.py`) |
| Feed UI / swipe / recommender | ⛔ Not started (Phases 4–6) |

**The immediate next action:** add a `YOUTUBE_API_KEY` to `.env` (Google Cloud →
enable YouTube Data API v3 → API key), then run the ingest job live
(`python -m scorekit.jobs.ingest --query "Clair de Lune"`) to confirm the first real
end-to-end slice writes cards to Supabase. The connector, persistence, and unit tests
already exist and pass; only the live API key is missing.

---

## 2. What scorekit is

A **Pinterest-style visual discovery platform for piano music.** Users browse or
search a feed of cards — each card is a YouTube tutorial/cover, an IMSLP score, or
a MuseScore listing — and a swipe-based like/skip system learns their taste over
time to personalize a home feed.

### The problem it solves
Piano learners face a two-part discovery gap no single tool covers:
1. **What to play next** is unguided — no taste-based discovery (by era, mood,
   difficulty, composer) the way Spotify/Pinterest do it for their domains.
2. **Finding the sheet music** once decided is fragmented across YouTube (tutorials/
   covers), IMSLP (free public-domain scores), and MuseScore (community listings),
   with no place that connects all three.

### Two feed modes, one system
- **Search feed** — query a specific piece → a mixed board of every card type found
  across all three sources.
- **Home feed** — no query → a personalized, ranked feed built from accumulated
  like/skip/dwell signal; defaults to a diverse spread for brand-new users.

---

## 3. Tech stack & architecture

- **Backend:** Python 3.13, scheduled ingestion jobs per source.
- **Storage:** Supabase (managed Postgres).
- **Containerization:** Docker (`Dockerfile` + `docker-compose.yml`).
- **Frontend (later, Phase 4+):** Pinterest-style masonry feed, swipe like/skip.
  Framework not yet chosen.
- **Deployment (later, Phase 7):** own domain/subdomain, linked from the personal
  site (`personalweb` repo → https://github.com/zdimitrov-dev/personalweb).

### Pipeline shape
`query → each Connector.search() → normalized Card objects → (Phase 1+) upsert
piece (by slug) + cards into Supabase → feed renders cards → user swipes →
interactions logged → (Phase 6) recommender ranks the home feed.`

---

## 4. Repository structure

```
scorekit/
├── PROJECT_CONTEXT.md      # ← this file (start here)
├── README.md               # public-facing overview, setup, phase plan
├── .env.example            # env var template (copy to .env, which is gitignored)
├── requirements.txt        # supabase, python-dotenv, httpx, tenacity,
│                           #   google-api-python-client, pytest
├── Dockerfile              # python:3.13-slim; entrypoint = ingest job
├── docker-compose.yml      # `docker compose run --rm ingest --query "..."`
├── db/
│   └── schema.sql          # full Postgres schema (idempotent). Apply to Supabase.
├── scorekit/               # the Python package
│   ├── __init__.py
│   ├── config.py           # env-backed Settings (Supabase / YouTube / Google CSE)
│   ├── db.py               # cached Supabase client (get_client())
│   ├── models.py           # Card, Piece, Interaction dataclasses (shared schema)
│   ├── normalize.py        # normalize_slug() — the cross-source dedupe key. TESTED.
│   ├── connectors/
│   │   ├── __init__.py     # Connector registry (CONNECTORS list, phase-ordered)
│   │   ├── base.py         # Connector ABC: .source + .search(query, limit)
│   │   ├── youtube.py      # STUB (Phase 1)
│   │   ├── imslp.py        # STUB (Phase 2)
│   │   └── musescore.py    # STUB (Phase 3)
│   └── jobs/
│       ├── __init__.py
│       └── ingest.py       # CLI orchestrator: runs connectors, collects Cards
└── tests/
    └── test_normalize.py   # unit tests for the slug normalizer
```

---

## 5. Data model (detailed — this drives the ML design)

Defined in `db/schema.sql`. Four tables + three enums. The mirroring Python
dataclasses live in `scorekit/models.py`.

### The core idea: separate *what* from *how*
A piano recommender answers two different questions that need different data:
1. **"Does this user like this *piece*?"** — taste/content (composer, era, mood,
   difficulty). Lives in `pieces` + `piece_tags`.
2. **"Does this user like this *presentation*?"** — format (tutorial vs performance,
   YouTube vs score, which channel). Lives in `cards` (`source`, `kind`, `author`).

`interactions` ties a user to both at once. This split lets the model **decompose**
a preference (`taste for piece × taste for format`), which means far more signal
per interaction — important early on, while interaction data is still sparse.

### `pieces` — canonical entity per real piece
`id, slug (unique), title, composer, era, genre, difficulty (smallint, nullable),
created_at, updated_at`
- **`slug`** is the normalized key (`debussy-clair-de-lune`) produced by
  `normalize_slug(title, composer)`. It makes a like on a YouTube video and a like
  on the IMSLP score of the *same piece* roll up to one `piece_id`. **Data
  efficiency is bounded by normalizer quality** — a miss fragments a user's signal.
- `composer/era/genre/difficulty` are content features and the basis for
  **cold-start** recommendations (a brand-new piece can be recommended immediately).
- `difficulty` is nullable → the model must handle "unknown difficulty."
- **Decision (2026-08-27): `difficulty` stays in the schema but is quarantined —
  nothing in the recommender may depend on it until we work out how to measure and use
  it properly.** Two reasons it needs care: (a) it is genuinely hard to measure, and
  (b) it is really a property of the *rendition*, not the piece — a simplified
  arrangement of *La Campanella* and the original differ enormously, even though
  *Twinkle Twinkle* will always be far easier than either. So `pieces.difficulty` is at
  most a coarse **piece-level prior** (how hard the canonical version is), while
  **per-rendition difficulty belongs in `cards.metadata`** (e.g. a MuseScore difficulty
  rating). Like `feed_position`, it is stored now and deliberately excluded from the
  first-pass model.

### `cards` — one row per result (what actually renders)
`id, piece_id (FK, on delete cascade), source, kind, external_id, url, title,
thumbnail_url, author, metadata (jsonb), created_at, unique(source, external_id)`
- **`source`** (`youtube|imslp|musescore`) and **`kind`**
  (`tutorial|cover|performance|score|listing`) are low-cardinality categorical
  presentation features (one-hot friendly).
- **`author`** (channel/arranger) is higher-cardinality signal → needs embeddings
  or target-encoding later.
- **`metadata jsonb`** is the escape hatch for source-specific fields (view count,
  duration, whether the description had a sheet-music link, MuseScore difficulty).
- **`unique(source, external_id)`** prevents duplicate ingestion (data hygiene).
- **Design principle: cards from different sources are NEVER merged** into one
  grouped result. Each is its own card in a mixed feed (like Pinterest).
  Normalization is quiet, behind the scenes, only via `piece_id`.

### `interactions` — the recommender's training signal (append-only event log)
`id (bigint identity), user_id (uuid, no FK yet), card_id (FK, on delete SET NULL),
piece_id (FK, on delete SET NULL), action, dwell_ms, feed_position, created_at`

This is the labeled training data. Key decisions (all intentional):
- **Both `card_id` and `piece_id` stored** (piece_id is derivable but denormalized)
  for (a) cheap training queries with no joins, and (b) **signal durability** —
  `card_id` is `SET NULL` on delete but `piece_id` survives, so if a YouTube video
  is removed you still keep "user liked that Chopin piece."
- **`action` enum = graded relevance, not boolean:**
  - `like` → strong positive
  - `click` → positive (opened the source resource; conversion intent)
  - `skip` → **the negative.** There is deliberately **no explicit dislike button**
    (TikTok-style: absence of engagement + a fast swipe-away is the negative).
- **`dwell_ms`** = engagement-intensity weight on top of the action: how long the
  card was in focus before acting. A fast skip is a strong negative; a long dwell is
  a confidence boost even without a like (watch-time-style implicit positive). It is
  **dwell time on the card in the feed**, comparable across all three sources.
  Nullable. (Video *watch-fraction* is richer but YouTube-only → belongs in
  `metadata` later, not this core column.)
- **`feed_position`** = 0-based rank of the card when shown. **Stored for
  position-bias correction later, intentionally NOT used by the first-pass model.**
- `bigint identity`, append-only: an event log built for volume + training.
- `user_id` is a bare uuid for now; will point at Supabase `auth.users` later.

### `piece_tags` — the feature store the recommender learns over
`piece_id (FK, on delete cascade), key, value, primary key(piece_id, key, value)`
- **Entity-attribute-value** design: `key` ∈ {composer, era, mood, difficulty, …},
  `value` is the tag. **Multi-valued** (a piece can be both `mood=melancholic` and
  `mood=romantic`). New feature types need **no migration** — just new rows.
- `idx_piece_tags_kv (key, value)` powers reverse lookup ("all pieces where
  era=romantic") = **candidate generation** for content-based recs and the diverse
  new-user feed.

### Enums
`card_source(youtube, imslp, musescore)` · `card_kind(tutorial, cover, performance,
score, listing)` · `interaction_action(like, skip, click)`

### Indexes
`idx_cards_piece(piece_id)` · `idx_interactions_user(user_id, created_at desc)` ·
`idx_interactions_piece(piece_id)` · `idx_piece_tags_kv(key, value)`

---

## 6. Recommendation engine plan (Phase 6)

**What this demonstrates (project framing).** scorekit is deliberately a showcase of the
two foundational recommender paradigms *and* the judgment to combine them:
- **Content-based filtering** — learning from *given* labeled tags (`piece_tags`:
  composer, era, mood, difficulty). Interpretable; solves cold-start.
- **Collaborative filtering** — learning latent taste from *other users' signals* (the
  `interactions` matrix). Scales; captures nuance no tag set can enumerate.
- **The hybrid / handoff** — the senior skill: knowing each one's failure mode and
  engineering the transition (content carries the low-data regime; collaborative is
  promoted once it beats the content+popularity baseline — see the data flywheel below).

The "separate *what* from *how*" schema (`pieces`/`piece_tags` vs. the `interactions`
log) was designed to support both from the start, so the data model itself is evidence
of the plan. Natural demonstration artifact: a head-to-head of content-only vs.
collaborative vs. hybrid on the same held-out interactions, with the same metrics.

The schema is built to support this progression, deliberately building up from
simple, interpretable baselines to more complex models rather than starting with a
black box:

1. **Candidate generation** — content (`piece_tags` reverse lookup) + collaborative
   (co-liked pieces).
2. **Feature assembly**
   - *User features* aggregated from `interactions` history: tag-affinity vector
     (weighted likes per era/composer/mood), source/kind preferences, difficulty
     distribution.
   - *Item features*: `piece_tags` + card `source`/`kind`/`author`/`metadata`.
3. **Labels + weights** — `action` is the label; `dwell_ms` is the confidence weight
   (implicit-feedback style, e.g. `confidence = 1 + α·log(1 + dwell_ms)`; a dwell
   above a threshold is an implicit positive even without a like).
4. **Model options (build up in this order):**
   - Popularity + tag-overlap heuristic → the cold-start / new-user diverse feed.
   - Logistic regression / gradient-boosted trees over engineered features →
     `P(like | user, card)`. Interpretable baseline.
   - ALS / matrix factorization on the implicit `user × piece` matrix (collaborative).
   - Two-tower embedding model (user tower / item tower) → the scalable version.
5. **Ranking + exploration** — score candidates, inject diversity so the feed isn't
   monotonous and to keep gathering exploration signal.

### ML considerations already accounted for / to remember
- **Cold start** is handled by content features (`piece_tags`) — the schema's key
  ML enabler. New pieces and new users both have a path.
- **`dwell_ms` must be normalized *within* `(source, kind)`** before use — 3s on a
  static score ≠ 3s on a 4-min video. Also cap/winsorize the top end (tab left open).
  Raw `dwell_ms` is the right thing to *store*; normalization is a feature step.
- **Position bias** is captured (`feed_position`) but quarantined from the first
  model on purpose. Introduce it deliberately later.
- **Temporal split** for train/test (use `created_at`) to avoid leaking the future.

### Features: given vs. learned (why sparse tags are not fatal)

A key reframe for the whole project. Every training example has two parts, and they
come from different places:

- **The label** = the interaction (`like`/`skip`/`click` + `dwell_ms`). We *have* this;
  it is genuine supervised signal. Logging it is easy. **This project is supervised
  learning, not unsupervised** — the "it feels unlabeled" worry is about missing
  *features*, not missing labels.
- **The features** = how a piece is represented. These can be **given** or **learned**:
  - **Given** — explicit tags in `piece_tags` (composer, era, mood…). Hard to obtain,
    especially for pop/modern pieces that no catalog describes.
  - **Learned** — latent embeddings inferred *from the interaction matrix itself*
    (collaborative filtering / matrix completion — the "Netflix Prize" approach). Sad
    pieces end up with similar vectors because the same people co-like them; a latent
    "sadness/energy" axis **emerges from behavior with no mood tag ever written.**

Consequences:
- The tag-quality problem is therefore a **cold-start** problem, not a fundamental
  blocker. Tags carry the **low-data** regime; learned features take over as
  interactions accumulate — and capture "mood" better than crude tags ever could.
- The two methods' weaknesses are **anti-correlated with the catalog**: classical =
  good tags / fewer plays → **content** carries it; pop/modern = poor tags / many plays
  → **collaborative** carries it. So we do *not* need to win the "hand-tag every pop
  song" fight.
- Third feature source for genuinely unlabeled pieces: **audio-derived features**
  (major/minor mode, tempo, energy, "valence" = a measured happy↔sad axis) computed
  from the recording itself — unsupervised extraction that needs no catalog or label.
  (Ready-made sources like Spotify's audio-features API are largely closed to new apps
  since late 2024, so plan to compute these from audio, e.g. librosa. Later refinement.)
- **Deferred:** a proper walkthrough of matrix completion / the Netflix-Prize analogy
  belongs with the Phase 6 build, not here.

### Evaluation & data bootstrapping (intended — not yet built)

**How we will know the recommender actually works.** The plan is an *offline*
evaluation: split `interactions` by `created_at` into a **temporal train/test split**
(train on the earlier events, test on the later ones — never a random shuffle, or the
model gets to "see the future"), fit the model on the train half, then measure how well
it predicts the held-out half — i.e. did it rank the pieces the user actually
liked/clicked above the ones they skipped.

- **The exact success metric is still open.** How to score "is it recommending well" is
  not yet decided — candidates are ranking metrics like precision@k / recall@k, NDCG,
  MAP, or AUC over the like/skip label. To be pinned down when the recommender is built.
  See Open questions.
- **Data scarcity is the first obstacle.** A fresh system has almost no interactions,
  and a taste model cannot be trained *or* evaluated without a meaningful volume of
  labeled swipes. We need a way to bootstrap a dataset:
  - **Manual dogfooding** — actually use the app and swipe. Honest signal, but slow: one
    human produces data at human speed.
  - **Synthetic generation via Claude (likely).** Define a handful of taste profiles and
    have Claude simulate users — generating large volumes of plausible like/skip/dwell
    interactions across the catalog far faster than a human could. Enough volume to
    exercise the pipeline and shake out the model. Caveat: synthetic taste only
    approximates real users, so results must be validated against real (manual) data
    before being trusted.

### Testing the recommender before we have a user base

The chicken-and-egg — "can't validate collaborative filtering without lots of users,
can't get users without shipping, can't ship without validating" — is resolved by not
requiring the data-hungry model to ship first. Four independent tools:

1. **Public benchmark datasets** — validate the CF *machinery* (ALS / matrix
   factorization / two-tower) is correct on established data with known baselines,
   *independent of scorekit's own data*: MovieLens (the canonical benchmark) and, closer
   to our domain, the Million Song Dataset / Last.fm Taste Profile (user × song implicit
   feedback, like our like/skip). If our model can't match published baselines here, the
   code is wrong — caught before any scorekit data exists.
2. **Synthetic ground-truth simulation** — generate an interaction matrix from a *known*
   latent taste model over our **real ingested pieces**: define K taste dimensions, give
   synthetic users taste vectors, draw likes via `P(like)=sigmoid(user·piece)+noise`.
   Because we know the true generating structure, we have perfect ground truth: does the
   model *recover* it and predict held-out likes? Claude makes the personas realistic
   (coherent "loves melancholic nocturnes, hates showpieces" users) rather than random.
   **Caveat:** generate with a *different/more complex* process than the model under test
   (nonlinearity, popularity bias, noise) or you rig the test; this validates the
   *mechanism*, never real human taste.
3. **Baselines + metrics** — always score against **random** and **most-popular**. A
   collaborative model that can't beat "just recommend the most popular pieces" is not
   working. Report precision@k / recall@k / NDCG / AUC plus coverage & diversity.
4. **The data flywheel (the actual launch plan)** — ship v1 with the **content/tag +
   popularity** model, which works at *zero* interaction history (cold-start by design)
   and is testable on small/synthetic data. It is useful on day one **and** generates
   real interactions. Train the collaborative model in the background on that accruing
   data, and **promote it only once offline evaluation on the real accumulated data
   beats the tag+popularity baseline.** So we never ship a model we haven't validated —
   we ship the one that provably works without data, and gate the data-hungry one behind
   a metric threshold measured on the data the live product itself produces. Optional
   accelerants: **warm-start** (pretrain on public data, fine-tune on ours) to need less
   of our own data, and a **closed beta** (piano community / dogfooding) to reach the
   hundreds-of-users range where collaborative filtering starts to bite.

### External data: benchmarking + warm-start (decision, 2026-08-27)

Two sanctioned roles for third-party listening data (e.g. MSD Taste Profile / Last.fm),
both bounded so the *live, shipped* model still learns primarily from scorekit's own
signal:

1. **Benchmarking (offline only)** — validate the collaborative machinery against known
   baselines; never part of the shipped product.
2. **Warm-start prior (cold-start only)** — when there is little signal about a user,
   external listening gives *marginally-better-than-random* recommendations, on the
   premise that general listening taste partially transfers to piano taste. As scorekit
   accumulates that user's own swipes — far more specific to their *piano* taste — the
   app's own signal takes over. Run it as an **ablation** ("cold-start with warm-start
   vs. without") so it demonstrates transfer learning rather than acting as a hidden
   crutch.

**This warm-start is collaborative, not content-based.** It rides on *item
co-occurrence* ("people who listen to piece A also listen to piece B"), not intrinsic
attributes (happy/sad/classical). It yields piece↔piece affinity, and the "separate
*what* from *how*" schema then carries that across formats: external data says A ≈ B
(the *what*); the user just engaged with the piano *cover* of A (the *how*, from our own
`cards`/`piece_id`), so recommend the piano *cover* of B. That cross-format hop is the
hybrid in miniature.

**Open sub-question — what seeds a brand-new user?** Aggregate external co-occurrence
only personalizes once the user has touched ≥1 piece here (then: its neighbors). True
zero-interaction personalization needs the *user's own* external history (e.g. linking a
Last.fm account — a consent/privacy step). Decide which warm-start seed to support.

---

## 7. Build phases roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Repo, Supabase schema, Docker skeleton | ✅ Done — schema applied to live Supabase (RLS on); Docker image still unbuilt |
| 1 | YouTube connector (first end-to-end slice) | 🟡 In progress — connector + persistence built & unit-tested; needs a live API key to run |
| 2 | IMSLP connector | ⛔ Confirm IMSLP terms before building |
| 3 | MuseScore via Google Custom Search (`site:musescore.com`, cached) | ⛔ |
| 4 | Search feed UI (mixed-card masonry) | ⛔ Framework TBD |
| 5 | Swipe interaction + logging (writes `interactions`; no ranking yet) | ⛔ |
| 6 | Recommendation engine / home feed | ⛔ |
| 7 | Polish + deploy (branding, domain, demo) | ⛔ |

Phases 0–4 are mostly mechanical pipeline work and should move quickly. Phases 5–6
are the most technically novel and deserve the most protected time — the main
scheduling risk is letting the earlier plumbing phases consume the time budgeted for
the recommender.

---

## 8. Current state in detail (what works vs what's a stub)

**Genuinely working:**
- `db/schema.sql` — complete, idempotent, final for V1. **Applied to the live Supabase project; RLS enabled on all four tables.**
- `scorekit/normalize.py` — `normalize_slug()` implemented and unit-tested
  (`tests/test_normalize.py`). Verified: `("Clair de Lune","Debussy") → debussy-clair-de-lune`.
- `scorekit/models.py` — `Card`, `Piece`, `Interaction` dataclasses (the shared schema).
- `scorekit/jobs/ingest.py` — CLI runs end-to-end (`python -m scorekit.jobs.ingest
  --query "..."`); iterates the connector registry, skips connectors that are not built
  or unconfigured (`NotImplementedError` / `ConnectorUnavailable`), and — unless
  `--dry-run` — upserts the piece + cards into Supabase via `scorekit/store.py`.
- `scorekit/connectors/youtube.py` — **implemented & unit-tested** (Phase 1): YouTube
  Data API search → normalized `Card`s, with `kind` heuristics and sheet-music-link
  capture in `metadata`. Needs a live `YOUTUBE_API_KEY` to hit the real API.
- `scorekit/store.py` — **implemented & verified live**: upserts pieces (by `slug`) and
  cards (dedup on `source,external_id`); unit-tested with a fake client.
- `scorekit/config.py`, `scorekit/db.py` — real code, **verified against the live
  Supabase backend** (connection + reads/writes confirmed).
- `Dockerfile` / `docker-compose.yml` — structurally complete; **image not built yet.**

**Stubbed / not started:**
- `imslp.py` and `musescore.py` connectors — `.search()` raises `NotImplementedError`
  (Phases 2-3). Zero API calls happen for those.
- No feed, UI, swipe logging, or recommender yet (Phases 4-6).

---

## 9. Local setup / dev

```bash
# 1. Env
cp .env.example .env            # then fill in the values (see below). .env is gitignored.

# 2. Apply schema to your Supabase project
#    Easiest: paste db/schema.sql into the Supabase dashboard SQL Editor and Run.
#    Or with a Postgres client: psql "$SUPABASE_DB_URL" -f db/schema.sql

# 3. Install + run
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m scorekit.jobs.ingest --query "Clair de Lune"

# Tests
pytest

# Docker
docker compose run --rm ingest --query "Clair de Lune"
```

### Environment variables (`.env`)
| Var | Purpose | Where to get it |
|---|---|---|
| `SUPABASE_URL` | Project URL | Supabase → Settings → Data API → Project URL |
| `SUPABASE_SERVICE_KEY` | Service-role key (**secret; bypasses RLS; never expose to frontend or commit**) | Supabase → Settings → API Keys → service_role |
| `SUPABASE_DB_URL` | Direct Postgres URI (used to apply schema) | Supabase → Settings → Database → Connection string (URI) |
| `YOUTUBE_API_KEY` | YouTube Data API (Phase 1) | Google Cloud console |
| `GOOGLE_CSE_ID` / `GOOGLE_CSE_KEY` | MuseScore via Google Custom Search (Phase 3) | Google Programmable Search Engine |

---

## 10. Conventions

- **Git — commit locally, do not push:** make local commits as you work, but never
  `git push`. The maintainer reviews and pushes.
- **Commit style:** concise imperative subject; body explaining the *why* when the
  change isn't obvious.
- **Secrets:** only ever in `.env` (gitignored). Never commit keys; never send the
  service-role key to the frontend.
- **Line endings:** repo is authored with LF; on Windows git may warn about CRLF
  conversion — harmless.

---

## 11. Open questions / decisions pending

- **Frontend framework** for the feed (Phase 4) — not chosen. The personal site is
  Next.js/TypeScript, so that's a natural candidate.
- **`users` table** — `interactions.user_id` is a bare uuid; wire it to Supabase
  `auth.users` when auth is added.
- **Scheduling** — ingestion is a CLI job today; the "scheduled jobs" story
  (cron/Supabase scheduled functions/etc.) is not yet built.
- **IMSLP terms** — confirm current access terms before building the Phase 2 connector.
- **Recommender evaluation metric** — how exactly to score "is it recommending well"
  (precision@k / NDCG / AUC / …) is not yet decided. See §6 → Evaluation & data
  bootstrapping.
- **Training-data bootstrapping** — how to accumulate enough interaction data to train
  and evaluate: manual dogfooding vs. Claude-generated synthetic interactions. See §6.
- **`difficulty` usage** — how to measure and actually use difficulty (piece-level prior
  vs. per-rendition in `cards.metadata`) is unresolved; quarantined from the model until
  then. See §5 → `pieces`.

---

## 12. External resources

- **scorekit repo:** https://github.com/zdimitrov-dev/scorekit
- **Personal site repo (`personalweb`):** https://github.com/zdimitrov-dev/personalweb
  — links to scorekit from its projects section (`src/lib/config.ts`).
- **Supabase dashboard:** https://supabase.com/dashboard

---

## Keeping this file current

This document is the project's living source of truth. Keep it in sync with the code
as the project evolves — update the **Status at a glance** table and **Current state
in detail** when something moves from stub to built, the **phases roadmap** when a
phase starts or finishes, **Open questions** as they're resolved, and the **Last
updated** date at the top. If something here no longer matches the code, fix it.
