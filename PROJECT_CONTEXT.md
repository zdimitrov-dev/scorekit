# scorekit — Project Context

> **If you are an AI assistant picking this project up on a fresh machine: read this
> file first, in full.** It is the single source of truth for what scorekit is, why
> it exists, how it is built, what is done, and what comes next. When you make a
> meaningful change to the project's state or direction, **update this file** (see
> [Keeping this file current](#keeping-this-file-current) at the bottom).

**Last updated:** 2026-08-21 · **Phase:** 0 complete → provisioning Supabase ·
**Repo:** https://github.com/zdimitrov-dev/scorekit

---

## 1. Status at a glance

| Area | State |
|---|---|
| Repo scaffold (Phase 0) | ✅ Done, committed, pushed to `main` |
| Database schema (`db/schema.sql`) | ✅ Written & final for V1 — **not yet applied to a live DB** |
| Supabase project | ⏳ **In progress** — being created; schema to be applied; `.env` to be filled |
| Docker image build | ⛔ Not built/verified yet (planned Phase 0 smoke test) |
| Source connectors | ⛔ Stubs only (raise `NotImplementedError`) |
| Feed UI / swipe / recommender | ⛔ Not started (Phases 4–6) |

**The immediate next action:** finish provisioning Supabase, apply `db/schema.sql`,
fill `.env`, then build the Docker image and run the ingest job as the Phase 0
smoke test. After that, Phase 1 (YouTube connector) is the first real feature.

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

## 3. Why this project exists (portfolio rationale — read before making design calls)

This is a portfolio project deliberately built to close a specific gap: strong data
engineering fundamentals but no demonstrated **ML / product-building** experience.
It is designed as **two separately defensible stories**:

- **Data engineering story:** multi-source ingestion pipeline (YouTube Data API,
  IMSLP, Google Custom Search), normalization into a shared schema, caching,
  scheduled jobs. An extension of prior group-project experience — this time solo.
- **AI/ML story:** a *genuine* recommendation engine trained on real interaction
  data — **not an LLM wrapper**. This is the actual differentiator and is given the
  most protected build time (Phase 6), rather than being rushed at the end.

**Design implication for any assistant:** favor decisions that make the ML story
real and legible (interpretable signal design, honest features, clear evaluation)
over clever shortcuts. The recommender is the point, not the plumbing.

---

## 4. Tech stack & architecture

- **Backend:** Python 3.13, scheduled ingestion jobs per source.
- **Storage:** Supabase (managed Postgres).
- **Containerization:** Docker (`Dockerfile` + `docker-compose.yml`).
- **Frontend (later, Phase 4+):** Pinterest-style masonry feed, swipe like/skip.
  Framework not yet chosen.
- **Deployment (later, Phase 7):** own domain/subdomain, linked from the personal
  portfolio site (`personalweb` repo → https://github.com/zdimitrov-dev/personalweb).

### Pipeline shape
`query → each Connector.search() → normalized Card objects → (Phase 1+) upsert
piece (by slug) + cards into Supabase → feed renders cards → user swipes →
interactions logged → (Phase 6) recommender ranks the home feed.`

---

## 5. Repository structure

```
scorekit/
├── PROJECT_CONTEXT.md      # ← this file (read first)
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

## 6. Data model (detailed — this drives the ML design)

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
per interaction — critical for learning from a small solo-project dataset.

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
- **`unique(source, external_id)`** prevents duplicate ingestion (ML data hygiene).
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

## 7. Recommendation engine plan (Phase 6 — the centerpiece)

Do not rush this phase. The schema is built to support this progression
(simplest → most impressive, which also tells a good "I built up, didn't jump to a
neural net" interview story):

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
     `P(like | user, card)`. Interpretable; strong portfolio baseline.
   - ALS / matrix factorization on the implicit `user × piece` matrix (collaborative).
   - Two-tower embedding model (user tower / item tower) → the scalable version.
5. **Ranking + exploration** — score candidates, inject diversity so the feed isn't
   monotonous and to keep gathering exploration signal.

### ML gotchas already accounted for / to remember
- **Cold start** is handled by content features (`piece_tags`) — the schema's key
  ML enabler. New pieces and new users both have a path.
- **`dwell_ms` must be normalized *within* `(source, kind)`** before use — 3s on a
  static score ≠ 3s on a 4-min video. Also cap/winsorize the top end (tab left open).
  Raw `dwell_ms` is the right thing to *store*; normalization is a feature step.
- **Position bias** is captured (`feed_position`) but quarantined from the first
  model on purpose. Introduce it deliberately later.
- **Temporal split** for train/test (use `created_at`) to avoid leaking the future.

---

## 8. Build phases roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Repo, Supabase schema, Docker skeleton | ✅ Scaffold done; Supabase provisioning in progress |
| 1 | YouTube connector (first end-to-end slice) | ⛔ Next real feature |
| 2 | IMSLP connector | ⛔ Confirm IMSLP terms before building |
| 3 | MuseScore via Google Custom Search (`site:musescore.com`, cached) | ⛔ |
| 4 | Search feed UI (mixed-card masonry) | ⛔ Framework TBD |
| 5 | Swipe interaction + logging (writes `interactions`; no ranking yet) | ⛔ |
| 6 | Recommendation engine / home feed — **the ML centerpiece** | ⛔ Protect this time |
| 7 | Polish + deploy (branding, domain, README, demo video) | ⛔ |

Phases 0–4 are mechanically similar to prior pipeline work and should move fast.
**Phases 5–6 are new territory and deserve the most protected time** — the biggest
risk to the plan is letting early plumbing eat the schedule for the differentiator.

---

## 9. Current state in detail (what works vs what's a stub)

**Genuinely working:**
- `db/schema.sql` — complete, idempotent, final for V1. *Not yet applied to a DB.*
- `scorekit/normalize.py` — `normalize_slug()` implemented and unit-tested
  (`tests/test_normalize.py`). Verified: `("Clair de Lune","Debussy") → debussy-clair-de-lune`.
- `scorekit/models.py` — `Card`, `Piece`, `Interaction` dataclasses (the shared schema).
- `scorekit/jobs/ingest.py` — CLI runs end-to-end (`python -m scorekit.jobs.ingest
  --query "..."`); iterates the connector registry and cleanly *skips* connectors
  that raise `NotImplementedError`, logging which sources are pending.
- `scorekit/config.py`, `scorekit/db.py` — real code; untested against a live
  backend because none is provisioned yet.
- `Dockerfile` / `docker-compose.yml` — structurally complete; **image not built yet.**

**Stubbed / not started:**
- All three connectors (`youtube.py`, `imslp.py`, `musescore.py`) — `.search()`
  raises `NotImplementedError`. Zero API calls happen.
- No persistence yet — `ingest()` collects `Card`s in memory and returns them; a
  `# TODO(Phase 1+)` marks where the Supabase upsert goes.
- No feed, UI, swipe logging, or recommender.

---

## 10. Local setup / dev

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

## 11. Conventions & decisions

- **Git identity:** commit as `Zarko <zarkodimitrovdev@gmail.com>` (set as the local
  `user.email` in this repo).
- **No AI attribution in commits.** Do **not** add a `Co-Authored-By: Claude` (or
  any AI) trailer, and don't mention AI authorship in commit messages. The owner
  explicitly does not want it.
- **Commit style:** concise imperative subject; body explaining the *why* when the
  change isn't obvious.
- **Secrets:** only ever in `.env` (gitignored). Never commit keys; never send the
  service-role key to the frontend.
- **Line endings:** repo is authored with LF; on Windows git may warn about CRLF
  conversion — harmless.

---

## 12. Open questions / decisions pending

- **Frontend framework** for the feed (Phase 4) — not chosen. The owner's personal
  site is Next.js/TypeScript, so that's a natural candidate.
- **`users` table** — `interactions.user_id` is a bare uuid; wire it to Supabase
  `auth.users` when auth is added.
- **Scheduling** — ingestion is a CLI job today; the "scheduled jobs" story
  (cron/Supabase scheduled functions/etc.) is not yet built.
- **IMSLP terms** — confirm current access terms before building the Phase 2 connector.

---

## 13. External resources

- **scorekit repo:** https://github.com/zdimitrov-dev/scorekit
- **Personal site repo (`personalweb`):** https://github.com/zdimitrov-dev/personalweb
  — links to scorekit from its projects section (`src/lib/config.ts`).
- **Supabase dashboard:** https://supabase.com/dashboard (owner's account).

---

## Keeping this file current

This file is the handoff contract between work sessions and devices. **When you
change the project's state or direction, update the relevant section here in the
same session** — especially:
- the **Status at a glance** table and **Current state in detail** when something
  moves from stub → built,
- the **phases roadmap** status column when a phase starts/finishes,
- **Open questions** as they're resolved,
- and the **Last updated** date at the top.

Keep it accurate over comprehensive: if something here no longer matches the code,
fix it. An assistant on another device is trusting this file to be true.
