# scorekit — Project Context

> **Start here.** This is the primary context document for scorekit — the design,
> current state, and roadmap in one place. Keep it in sync with the code as the
> project evolves (see [Keeping this file current](#keeping-this-file-current)).

**Last updated:** 2026-08-31 · **Phase:** all three connectors live (YouTube, IMSLP, MuseScore/Tavily); **Phase 4 feed UI (`web/`) with live streaming search — in progress** ·
**Repo:** https://github.com/zdimitrov-dev/scorekit

---

## 1. Status at a glance

| Area | State |
|---|---|
| Repo scaffold (Phase 0) | ✅ Done, committed, pushed to `main` |
| Database schema (`db/schema.sql`) | ✅ Applied to live Supabase; RLS enabled on all tables |
| Supabase project | ✅ Provisioned — schema applied, RLS on, `.env` filled & connection verified |
| Docker image build | ⛔ Not built/verified yet |
| Source connectors | ✅ All three **live** — YouTube; IMSLP (search + enrichment, gated by `IMSLP_ENABLED`); MuseScore via Tavily (gated by `TAVILY_API_KEY`) |
| Attribution + enrichment | ✅ Match-scoring filter (`scorekit/matching.py`) + IMSLP enrichment (license, instrumentation, style, year) |
| Persistence (ingest → Supabase) | ✅ Built & verified live (`scorekit/store.py`) |
| Feed UI (Phase 4) | 🟡 In progress — Next.js app in `web/` (masonry board, bottom nav, click-to-expand modal, like/save); reads Supabase server-side |
| Piece tagging (`piece_tags`) | ✅ Derived from cards by `scorekit/tagging.py` (job: `scorekit.jobs.tag_pieces`) |
| Recommender — content-based | ✅ Live — ranks the home feed (`scorekit/recommend.py`, `POST /recommend`); signals still from localStorage |
| Swipe logging / collaborative filtering | ⛔ Not started (Phase 5, then the collaborative half of Phase 6) |

**The immediate next action:** **Phase 5 — real interaction logging** (auth + writes to
`interactions`), which is what the collaborative half of the recommender needs. The
**content-based recommender is live** (see §6a): Home is ranked by tag affinity, but its
signals still come from the browser's localStorage, so there is no cross-device or
cross-user history to learn from yet.

Open refinements elsewhere: YouTube `kind` via an LLM (see Open questions), the
same-name/different-composition attribution residual, per-movement labeling (a resolved
movement lands on its parent-work page), IMSLP thumbnails/PDF links, and **query
normalization** so "Clair de Lune" and "Debussy Clair de Lune" resolve to one piece (they
are separate slugs today; a bare opus query like "Op 48 No 1" also returns no IMSLP,
because IMSLP's pages are titled by piece + composer).

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

- **Backend:** Python 3.13 — the ingestion pipeline per source, plus a **FastAPI HTTP API**
  (`scorekit/api.py`) the frontend calls for live/streaming search.
- **Storage:** Supabase (managed Postgres).
- **Containerization:** Docker (`Dockerfile` + `docker-compose.yml`).
- **Frontend (later, Phase 4+):** Pinterest-style masonry feed, swipe like/skip.
  Framework not yet chosen.
- **Deployment (later, Phase 7):** own domain/subdomain, linked from the personal
  site (`personalweb` repo → https://github.com/zdimitrov-dev/personalweb).

### Pipeline shape
`query → each Connector.search() → normalized Card objects → attribution match-filter
(score vs. the queried piece, drop clear non-matches) → IMSLP enrichment + disambiguation
resolution (work-page license/instrumentation/style; signpost pages → real score pages)
→ upsert piece (by slug) + cards into Supabase → feed
renders cards → user swipes → interactions logged → (Phase 6) recommender ranks the
home feed.`

---

## 4. Repository structure

```
scorekit/
├── PROJECT_CONTEXT.md      # ← this file (start here)
├── AGENTS.md               # agent guidance (read context first; commit locally, don't push)
├── CLAUDE.md               # pointer to AGENTS.md for Claude Code
├── README.md               # public-facing overview, setup, phase plan
├── .env.example            # env var template (copy to .env, which is gitignored)
├── requirements.txt        # supabase, python-dotenv, httpx, tenacity,
│                           #   google-api-python-client, pytest
├── Dockerfile              # python:3.13-slim; entrypoint = ingest job
├── docker-compose.yml      # `docker compose run --rm ingest --query "..."`
├── db/
│   └── schema.sql          # full Postgres schema + RLS (idempotent). Applied to Supabase.
├── scorekit/               # the Python package
│   ├── __init__.py
│   ├── config.py           # env-backed Settings (Supabase / YouTube / IMSLP / Tavily)
│   ├── db.py               # cached Supabase client (get_client())
│   ├── models.py           # Card, Piece, Interaction dataclasses (shared schema)
│   ├── normalize.py        # normalize_slug() — the cross-source dedupe key. TESTED.
│   ├── store.py            # upsert_piece / upsert_cards → Supabase. TESTED.
│   ├── matching.py         # attribution match-scoring; drop clear non-matches. TESTED.
│   ├── tagging.py          # derive piece_tags (composer/era/style/instrumentation/form). TESTED.
│   ├── recommend.py        # content-based ranker: profile → affinity → popularity → diversity. TESTED.
│   ├── api.py              # FastAPI: /search, /search/stream (NDJSON), /recommend
│   ├── connectors/
│   │   ├── __init__.py     # Connector registry (CONNECTORS list, phase-ordered)
│   │   ├── base.py         # Connector ABC (.source + .search) + ConnectorUnavailable
│   │   ├── youtube.py      # Phase 1 — implemented, tested, live
│   │   ├── imslp.py        # Phase 2 — search + work-page enrichment, gated by IMSLP_ENABLED
│   │   └── musescore.py    # Phase 3 — Tavily search (site:musescore.com) + per-query cache, gated by TAVILY_API_KEY
│   └── jobs/
│       ├── __init__.py
│       ├── ingest.py       # CLI orchestrator: search → match-filter → enrich → persist
│       └── tag_pieces.py   # rebuild piece_tags from stored cards (idempotent)
├── tests/
│   ├── test_normalize.py   # slug normalizer
│   ├── test_store.py       # persistence upserts (fake client)
│   ├── test_matching.py    # attribution match-scoring + filter
│   ├── test_youtube.py     # YouTube parsing/enrichment + connector
│   ├── test_imslp.py       # IMSLP parsing, enrichment, connector
│   ├── test_musescore.py   # MuseScore Tavily mapping, cache, gate
│   ├── test_api_stream.py  # per-source search cache (negative-cache regression)
│   ├── test_tagging.py     # tag derivation + the corroboration rules
│   └── test_recommend.py   # profile, IDF, affinity, cold start, diversity
└── web/                    # Phase 4 — Next.js feed app (App Router, Tailwind, framer-motion)
    ├── app/                # pages: / (home feed), /search, /settings; api/ proxies
    ├── components/         # Feed, PieceCard, CardModal, BottomNav, SearchFeed, HomeFeed
    └── lib/                # supabase (server), cards, types, useCollection
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

## 5a. Interaction logging — **built** (`web/lib/track.ts`, `POST /interactions`)

The dataset the learned ranker (§6b) will train on. Nothing existed before this: the
`interactions` table was empty and likes lived only in `localStorage`, so there were no
labelled examples of *(piece features → liked)* at all.

**Identity.** An anonymous per-browser UUID in `localStorage`. No account, no PII — enough
to group one person's history, and replaceable by a real user id when auth lands without a
schema change. It must be a **UUID**, because `interactions.user_id` is a uuid column and
anything else makes Postgres reject the entire batch.

**What is logged.** `seen` when a card is genuinely viewed, `click` when it is opened (with
how long it stayed open), `like`, `save`. `db/migrations/001` **is applied**, so `seen`
stores as `impression` and `save` is distinct from `like`. `impression` is deliberately not
`skip`: once an explicit reject control exists, "passed over" and "rejected" carry
different confidence, and collapsing them at write time would be unrecoverable.

> **Do not clear the `cards` table once real interactions exist.** `interactions.card_id`
> is `on delete set null`, so wiping the corpus preserves the events but severs them from
> the features they describe — the labels survive as unusable rows.

**Negatives come from impressions**, since the feed has no reject control: a card shown and
passed over is the contrast a classifier needs. Quality of that signal took three fixes,
each found by inspecting what actually landed in the table:
- **Visibility, not rendering.** ≥50% visible for ≥900ms, via `IntersectionObserver`, so a
  card that flew past during a fast scroll is not recorded as considered-and-rejected.
- **Dwell measured on exit, not at the threshold.** Logging when the card first qualified
  made every row report the same ~900ms — the column carried no information whatsoever,
  though dwell is the entire point: it separates lingering from scrolling past.
- **A settle timer.** A card that never leaves the viewport was never recorded, so the top
  of the feed — the most reliably *seen* part — was the least logged. Cards still visible
  after 8s are written then, which right-censors those dwell values at 8000ms; shorter
  visits still record their true duration.

Sub-400ms modal opens are discarded as mis-clicks; without that, React's development
double-invoked effects were writing 1ms "views" into the training data.

**Delivery.** Events queue and flush on a timer, and on the way out via `sendBeacon` —
`fetch` is cancelled at unload and would silently drop the tail of every session. All
failures are swallowed: this is telemetry, so a broken logger may cost some training data
and must never cost the user their action.

---

## 6a. Content-based recommender — **built** (`scorekit/tagging.py`, `scorekit/recommend.py`)

The non-collaborative half is live and powers the home feed. It was built first on
purpose: collaborative filtering can say nothing about a user with no neighbours or a
piece nobody has touched, and this project starts with one user and a corpus that grows
one search at a time. Content-based ranking works from the very first like, so it is both
the launch ranker and — later — the cold-start fallback the collaborative model defers to.
The two compose as `score = w·content + (1-w)·collaborative`.

**Feature extraction (`scorekit/tagging.py`, job: `python -m scorekit.jobs.tag_pieces`).**
Derives `piece_tags` from a piece and its cards: `composer`, `era`, `style`,
`instrumentation` (a controlled vocabulary, not IMSLP's free text), `form` (nocturne,
prelude, fugue…), `public_domain`. Tagging at the **piece** level is what makes uneven
enrichment work: a YouTube card knows nothing about the music, but one IMSLP card carries
style and instrumentation, and because both share a `piece_id` the whole piece — bare
YouTube cards included — becomes rankable. Re-run the job after any vocabulary change; it
replaces tags per piece, so it is idempotent and leaves no stale rows.

Three lessons are baked into it, each found by running it over the real corpus:
- **Only high-confidence cards define a piece** (`match_score >= CONFIDENT_MATCH`). The
  attribution filter keeps loose neighbours on purpose; letting them describe the piece
  tagged Debussy's "Clair de lune" a *rag*.
- **Composer is voted, not taken from one row.** IMSLP's `author` names the *arranger* on
  a derivative, which made "Moonlight Sonata" come out as Ramón León Egea. Known composer
  surnames appearing across card titles outvote a lone author.
- **A value needs corroboration** (≥2 cards) unless the piece's own title says it. One
  ragtime cover or one orchestral transcription must not redefine the work.

**`format` (tutorial / cover / performance)** is what a piece's cards mostly *are*. It is a
real taste dimension — wanting to learn a piece is not the same as wanting to hear it — and
unlike composer or creator it generalises across pieces. It is also the only feature a
non-classical entry may have: a "Coldplay piano" search had 45 cards and **zero** tags, so
it could never be recommended or learned from however often it was liked. `score` and
`listing` are excluded, since they describe the source rather than the music.

A fourth rule came from testing artist queries: **a dominant YouTube channel becomes a
`creator` tag.** Searching "Patrik Pietschmann" produces a piece with no composer, era or
form, which carried *no features at all* and could never influence the feed however often
it was liked. A channel holding ≥50% of a piece's videos (min 3) is what that entry is
about, so it is tagged as such; a normal spread of performers yields no `creator`.

**Ranking (`scorekit/recommend.py`, endpoint: `POST /recommend`).** Four steps:
profile → score → blend → diversify.
- **Profile:** liked/saved pieces become a weighted tag vector. `save` (1.5) outweighs
  `like` (1.0); `skip` is the negative (−0.8) — there is no dislike button. The vector is
  L2-normalised so a heavy user isn't compared on a different scale to a new one.
- **Rescale before blending:** affinity and popularity are min-maxed across the candidate
  pool first, or `POPULARITY_WEIGHT` is not a real proportion. Raw cosine between two
  genuinely related pieces is ~0.15 however related they are (they share one tag of
  three), while any popular video sits at 0.75–0.85 popularity — so blending directly let
  popularity outweigh the *best possible* tag match, and the "personalized" feed was a
  popularity feed with a nudge.
- **Score:** tag affinity weighted by **IDF × `KEY_WEIGHTS`**. IDF measures rarity;
  `KEY_WEIGHTS` measures what a *kind* of tag says about taste, and the two are not the
  same. Sharing a composer means far more than sharing an instrument — and in piano
  repertoire almost everything involves a piano. With IDF alone, a heterogeneous entry
  that had accumulated many incidental tags (the "Rousseau" artist search, 15 tags)
  matched every profile through low-information overlap and outranked genuine neighbours:
  liking Debussy surfaced it above Satie, who shares the era.
- **Blend:** a small popularity prior (`POPULARITY_WEIGHT = 0.15`, log-scaled views) so a
  thin profile still ranks sensibly. Taste dominates by design.
- **Diversify:** a greedy MMR pass penalising already-shown pieces and composers, so the
  board reads like a feed rather than 20 cards of one piece.

Every returned card carries a `metadata.rec` breakdown (`affinity`, `popularity`,
`score`) so the ordering can be explained and debugged instead of being opaque.

- **Diversify:** repeats fade **multiplicatively** (`PIECE_DECAY`, `GROUP_DECAY`), plus a
  hard `MAX_CONSECUTIVE_PER_PIECE` ceiling. Subtracting a flat penalty was wrong in both
  directions: scores live in [0, 1] after rescaling, so a penalty big enough to prevent a
  wall drove the *second* card of a liked piece to zero — liking several Birru uploads
  surfaced exactly one and buried the rest, which reads as the likes being ignored — while
  a penalty small enough to avoid that let one piece own the board. A decay has no such
  cliff; the ceiling makes the variety guarantee absolute even when everything else scores
  near zero (a thin corpus, or a profile nothing else matches).
- **Engaged *cards* are held back, not their pieces.** Excluding the whole piece meant
  liking a Liszt étude removed every Liszt card from the feed. Liking something should
  surface more of it.

**Tagging runs at ingest, not only as a batch job.** `store.retag_piece()` is called per
source inside `_ingest_stream` (per source rather than once at the end, since a client
disconnecting mid-stream would otherwise leave a piece ingested but untagged). Leaving it
to the batch job meant every piece searched since the last run had zero affinity and was
silently unrecommendable — which is what made a freshly-searched Liszt piece impossible to
promote no matter how many of its cards were liked.

**Current limitation — where the signals come from.** `POST /recommend` takes signals in
the request body because likes/saves still live in `localStorage` (auth is Phase 5). The
ranker is indifferent to their origin, so switching to the `interactions` table is a
change in `api.py` only, not in the algorithm.

Verified end-to-end through the UI with a composer absent from the corpus: searching
**Grieg**, liking four cards from the results, then opening Home gives a board whose top
three cards are all Grieg, followed by romantic neighbours (Liszt, Chopin, Rachmaninoff)
and more Grieg at slot 8 — the consecutive ceiling visibly at work. Home re-ranks on every
mount, and a **Refresh feed** control rebuilds it on demand.

---

## 6b. Learned ranker (next) — planned design

A supervised model to sit **alongside** the content-based ranker, not replace it, so the
project can show the heuristic and the learned model measured head-to-head on the same
held-out interactions. The tag ranker weights features by `KEY_WEIGHTS`, which are numbers
*chosen by hand*; the learned model derives them from behaviour, and the comparison is the
interesting result either way.

**Blocked on data, not code.** §5a now produces the dataset; a few real sessions are needed
before any accuracy number means anything.

**Model choice for this data regime** — sparse categorical tags plus a few numerics,
hundreds of interactions rather than millions:
- **Logistic regression** as the mandatory baseline. At this size it frequently beats
  richer models, and its coefficients are directly comparable to `KEY_WEIGHTS`, so it
  either validates those weights or corrects them.
- **Gradient-boosted trees / random forest** as the main model: handles the categorical +
  numeric mix, tolerates small *n* with depth limits, captures interactions a linear model
  cannot ("romantic AND nocturne"), and exposes feature importances.
- **Neural nets are deferred, deliberately.** Two-tower embedding models are what
  production recommenders use, but they need roughly 10⁴–10⁶ interactions; below ~1,000 a
  net overfits and loses to logistic regression while costing all interpretability. Revisit
  at that volume, not before.

**Labels.** Positive: `like`, `save`, and long-dwell `click`. Negative: `seen` with short
dwell. Dwell weights the examples rather than being a feature, since it is only observed
*after* a card is shown and is unavailable at scoring time.

**Serving.** A third stage in the cascade, with content-based as the cold-start fallback
for any user or piece the model has not seen — which, on a corpus that grows one search at
a time, is a permanent condition rather than a temporary one.

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
| 1 | YouTube connector (first end-to-end slice) | ✅ Working end-to-end live (search + enrich + persist); refinements open (pagination, richer kind, stale-card reconcile) |
| 2 | IMSLP connector | ✅ Live + enriched + **disambiguation resolution** (Option A), gated by `IMSLP_ENABLED` (terms confirmed). Open: per-movement labeling, thumbnails/PDF links |
| 3 | MuseScore via Tavily search (`include_domains=musescore.com`, cached) | ✅ Live and verified against the API (score-preview thumbnails rebuilt via the CDN). (Switched off Google CSE, which is closed to new projects.) Open: pagination, uploader/instrumentation parsing |
| 4 | Feed UI (mixed-card masonry) | 🟡 In progress — Next.js `web/`: masonry board, bottom nav, framer-motion expand modal, like/save (localStorage), live streaming search + sorts + recent searches. Open: swipe, source-diversity ranking |
| 5 | Swipe interaction + logging (writes `interactions`; no ranking yet) | ✅ Logging live (see §5a) — impressions, dwell, likes/saves, modal step-through. Explicit swipe-to-reject UI still open |
| 6 | Recommendation engine / home feed | 🟡 **Content-based half built and live** (see §6a) — tags + IDF affinity + popularity prior + diversity, ranking the home feed. Collaborative half awaits Phase 5 signal |
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
- `scorekit/connectors/youtube.py` — **implemented, unit-tested & verified live** (Phase 1):
  two-step `search.list` + `videos.list` → normalized `Card`s with full-description
  sheet-music-link capture, `duration_seconds`/`view_count` in `metadata`, a compilation
  flag (`is_compilation`, tunable threshold; word-boundary title cues), `kind` heuristics,
  and exclusion of auto-generated `- Topic` channels.
- `scorekit/store.py` — **implemented & verified live**: upserts pieces (by `slug`) and
  cards (dedup on `source,external_id`); unit-tested with a fake client.
- `scorekit/connectors/imslp.py` — **live & enriched (Phase 2), gated by `IMSLP_ENABLED`
  (terms confirmed).** MediaWiki search → `score` cards with composer parsed from the
  `Title (Surname, Forename)` convention (incl. unicode); redirect pages filtered; page
  title is the `external_id` (IMSLP search omits `pageid`). `enrich(card)` fetches the
  work page and adds per-file **license** (Public Domain / CC), **instrumentation**
  (e.g. `piano` vs `Guitar` — usable to filter non-piano), **piece_style**, **year**,
  the **first-page score thumbnail** (resolved via the `imageinfo` API when the work page
  has one), and `has_scores` / `is_public_domain` / `is_disambiguation` flags. `enrich_cards(cards)`
  additionally **resolves disambiguation pages** into the real work-page cards they point
  to (parses `LinkWork` templates — the ingest pipeline calls this). Unit-tested.
- `scorekit/matching.py` — **attribution match-scoring** (`tests/test_matching.py`).
  Scores each card against the queried piece and stores `metadata['match_score']`, dropping
  only clear non-matches (`DROP_THRESHOLD`, lenient — lesser/related works survive at a lower
  score). Runs before enrichment. The score blends token **overlap** with the **longest
  contiguous run** of query tokens (weighted 0.4/0.6 — word order carries the phrase), plus a
  composer-surname boost. Opus/movement **numbers** are handled by contradiction, not absence:
  a card naming a *different* opus is penalised hard (`×0.1–1.0` by matched fraction), while a
  card naming no number at all is only nudged (`×0.6`), since it may be the same piece
  described by key. `annotate_and_filter` also records each card's `metadata['rank']` (the
  connector's own relevance position) — the feed uses it to break `match_score` ties.
  *Why continuous:* an earlier bucketed score returned 1.0/0.5/0.4 for nearly everything, so
  the feed's "Best match" collapsed into whatever its tiebreak was.
- `scorekit/config.py`, `scorekit/db.py` — real code, **verified against the live
  Supabase backend** (connection + reads/writes confirmed).
- `Dockerfile` / `docker-compose.yml` — structurally complete; **image not built yet.**

**IMSLP disambiguation resolution (done — Option A):** many search hits are
**disambiguation pages** (signposts with no scores) or **redirects** — e.g. the famous
Debussy "Clair de lune" result is a disambiguation page pointing at *Suite bergamasque,
CD 82* plus two song settings. `enrich_cards()` **resolves** these: it parses the page's
`LinkWork`/`LinkWorkN` templates and replaces the dud card with the real work-page cards
(each keeps the searched title, links to the actual score page, and carries its own
enrichment). Verified live: Debussy "Clair de lune" → the Suite bergamasque piano score
(`instrumentation='piano'`) + the two song settings (`voice, piano`). Remaining nicety:
a movement resolves to its **parent-work** page (Clair de lune is track 3 of the suite),
so a "from {parent_work}" label / movement anchor is future UX (`parent_work` is stored).

- `scorekit/connectors/musescore.py` — **Phase 3, live**, gated by `TAVILY_API_KEY`. Queries the
  **Tavily search API** with `include_domains=["musescore.com"]` → `kind="listing"` cards.
  Per-query TTL **file cache** stays within Tavily's free budget (~1,000/mo); auth/quota errors
  (401/403/429) → skip. *Why Tavily:* the original Google Custom Search JSON API is **closed to new
  projects** (shutdown Jan 1 2027) — that was the persistent 403; Vertex AI Search is Google's
  successor but enterprise-priced/complex, so Tavily (recurring free tier + native domain
  filtering) was chosen. Deferred: pagination, instrumentation parsing, DB-backed cache.
  - **Thumbnails (~90% coverage, measured over 107 cards).** A result's `images` are just
    everything scraped off the listing page — mostly the "Pro" sale banner, app-store
    badges and ad pixels. Only the entry matching `/scoredata/g/<hash>/score_0` is the
    engraving, and its `musescore.com/static/...` URL **403s when hotlinked**, so
    `_thumbnail` rebuilds the hash into a sized CDN URL
    (`cdn.ustatik.com/...score_0.png@600x840`). Three sources are tried in order, because
    `images` alone finds it only about a third of the time: `images` → `raw_content` (page
    HTML Tavily already fetched) → one batched `/extract` call at `advanced` depth for
    whatever is still missing. MuseScore answers *our* direct requests with 403, so we
    never fetch the page — extract goes through Tavily's own infrastructure. Still
    `None` → the feed's titled tile, which beats showing a promo banner.
  - `CACHE_VERSION` is part of the query cache key. Improved extraction was otherwise
    masked for 30 days by entries built with the older logic: coverage stayed at ~20% on
    every already-cached query until this existed.

**Framework laid, inert (needs config):**

**Stubbed / not started:**
- IMSLP thumbnails & direct PDF links — served via IMSLP's hashed file system, not
  exposed by the API; deferred.
- Swipe logging (Phase 5) and the recommender (Phase 6) not started.

**Phase 4 feed UI — `web/` (in progress):**
- Next.js (App Router) + Tailwind v4 + framer-motion + lucide, in `scorekit/web/`.
  Reads Supabase **server-side** with the service key (no secret in the browser);
  `web/.env.local` holds `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` (gitignored).
- Masonry board (`columns-2 md:3 xl:4`), hover-darken titles, source/duration badges.
  IMSLP cards show the **real first-page score thumbnail** when resolved, else a themed
  score tile (composer, title, and stat chips: instrumentation / style / year / PD).
  24 then "Load more".
- Fixed **top bar** (wordmark left, profile menu right — the menu holds Sign-in stub,
  Your profile, Saved, Settings) and fixed **bottom nav** (Home / Search / Saved). Pages:
  `/` = the **home / recommendation feed** (mixed board of everything, stand-in for the
  Phase 6 recommender). `/search` runs a **live search** — it submits to the API, which
  ingests the piece on demand (cached pieces return instantly) and **streams results per
  source (NDJSON)** so cards roll out as they arrive (videos first, then scores). It
  **separates YouTube (the centerpiece masonry board) from a slide-out one-column *scores*
  drawer** (IMSLP + MuseScore, in-page, own scroll, pushes the board left on large screens),
  with **sort controls** (Best match / Most viewed / Newest). Clicking into the search box
  offers the **last 4 searches** (localStorage, most-recent-first; opened on click as well as
  focus, since after a search the input is already focused). `/favorites` (liked+saved
  from localStorage), `/profile` (scaffold), `/settings` (stub).
- **Sort tiebreaks matter:** "Best match" breaks `match_score` ties on the source's ingest
  `rank`, never on view count — tying back to views made it render an identical board to
  "Most viewed" whenever scores clustered, which read as a broken toggle.
- `PieceCard` falls back to the themed tile at **runtime**, not just when `thumbnail_url` is
  null: an image that errors (dead/hotlink-blocked) or loads below 160×120 is treated as
  absent, so a stamp-sized or broken image never lands in a masonry column.

**Not every query names a piece.** `match_score` also scores the query against the card's
**author** (`_names_author`). Searching an artist ("Birru", "Rousseau", "Patrik
Pietschmann") returns that channel's uploads, whose titles never contain the artist's
name — scoring titles alone gave all of them 0.0 and the filter discarded a perfect result
set. The match is all-or-nothing: every query token must appear in the author **in order**,
as a whole token or the start of one, so shortened names work the way people type them —
"Kat Cordova" names *Katherine Cordova*. Demanding an exact contiguous run instead dropped
11 of 12 correct results for that search. It stays precise because order is required and a
prefix needs three characters, so "Piano Sonata" does not name a channel called "Piano
Tutorials" and cannot rescue a card the title rejected. Verified live: a cold "Patrik
Pietschmann" search returns 23 of 24 cards from that channel; "Kat Cordova" returns 24.

**Search caching (`_ingest_stream`) — cache on cards, per source, never on the piece row.**
The stream used to decide "already ingested" from the existence of the *piece* row, so a piece
whose ingest stored nothing (connector down, out of quota, or rows removed later) became a
permanent **negative cache**: every repeat search replayed zero batches and the UI reported
"No results" forever for a query that had worked before. It now replays only sources that
actually have cards and ingests the rest, which also lets a source that was unavailable on the
first search fill itself in later. Regression-tested in `tests/test_api_stream.py`. Retrying a
missing source is cheap in practice (YouTube is effectively never missing, IMSLP is free, and
Tavily repeats hit the local file cache), so no attempt-tracking column was added.

Cards also carry `metadata.mv` (`matching.MATCHER_VERSION`), and a source whose cards were
scored by superseded matching is re-ingested rather than replayed. **Dropped cards are
never stored**, so a scoring fix cannot be applied by re-scoring the database — the results
it should now keep were discarded at ingest, and only a re-fetch recovers them. Bump
`MATCHER_VERSION` whenever scoring changes *which* cards are kept. Without it, adding
author matching fixed artist queries for new searches while an already-cached "Birru" went
on returning the single wrong card it had matched by title.

**Masonry uses explicit columns, not CSS `columns-*`.** CSS multi-column re-flows its whole
content when items are appended, so "Load more" visually reshuffled every card on screen.
`Feed` assigns each card to the measurably shortest column once and never moves it;
verified with 0 of 72 cards changing position across a Load more.

A fresh list is placed as though the columns were **empty rather than measured**: the reset
has not painted when the placement effect runs, so the DOM still holds the previous board,
and its tall columns pushed new cards into whichever columns the old list happened to leave
short — a two-result search rendered into columns 3 and 4 with 1 and 2 blank.

`Feed` identifies its list by a **signature of card ids, never by array identity**. Callers
build these arrays during render (`sortVideos(...)`, a filter), so the reference changes on
every parent re-render — including the one caused by opening a card. Keying the layout
reset on identity wiped the board on click and unmounted the card mid-transition, which is
why the modal appeared not to open at all. The callers memoize their arrays too.

**The recent-searches panel opens on click, not focus.** The search input autofocuses, so
opening on focus put the panel over the top row of results on every visit to `/search` and
swallowed clicks meant for those cards.
- **API (`scorekit/api.py`, FastAPI):** `GET /search` (blocking) and `GET /search/stream`
  (NDJSON per-source batches, each persisted before streaming). The Next route
  `/api/search` proxies the stream server-to-server (`web/.env.local` `SCOREKIT_API_URL`
  points at it; defaults to `http://localhost:8000`).
- Click-to-expand modal via framer-motion shared `layoutId`: the card morphs to cover
  most of the page (content left, info right — title link, sheet link, badges, placeholder
  comments, Like/Save via localStorage), and the X animates it back.
- **Run both servers with one command** — the root `package.json` dev launcher (uses
  `concurrently` + `scripts/dev-api.mjs`, which finds the venv Python cross-platform):
  ```
  npm install        # once, at the repo root — installs concurrently
  npm run dev        # starts web (:3210) + api (:8000) together; Ctrl+C stops both
  ```
  (First-time web setup: `cd web && npm install`, and the API needs the venv +
  `pip install -r requirements.txt`.) Verified live against the real DB.

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
| `IMSLP_ENABLED` | Enable the IMSLP connector (Phase 2); inert until set (`1`/`true`). Confirm IMSLP terms first | no key needed (public MediaWiki API) |
| `TAVILY_API_KEY` | Enables the MuseScore connector (Phase 3); inert until set | tavily.com — free tier ~1,000 searches/month |

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

- **Frontend framework** — ✅ resolved: Next.js (App Router) + Tailwind + framer-motion,
  in `web/`.
- **Feed source diversity** — the feed sorts by relevance then popularity, which clusters
  the high-view YouTube cards first and pushes IMSLP score cards to the end. A
  source-diversity / interleave re-rank would make the board feel more mixed.
- **Live search → ingestion** — ✅ done: `/search` submits to the FastAPI, which ingests a
  brand-new piece on demand and streams results per source. Remaining polish: the freeform
  query is slugged as-is (so "Clair de Lune" and "Debussy Clair de Lune" are different
  pieces); a composer field or fuzzy piece-matching would unify them.
- **Auth for like/save + interactions** — likes/saves persist to `localStorage` for now.
  Wiring them (and swipe logging, Phase 5) to Supabase needs the `users` table / auth.
- **Reads via service key vs public RLS** — the feed reads server-side with the service
  key; switching to a public-read RLS policy + anon key would allow direct client reads.
- **`users` table** — `interactions.user_id` is a bare uuid; wire it to Supabase
  `auth.users` when auth is added.
- **Scheduling** — ingestion is a CLI job today; the "scheduled jobs" story
  (cron/Supabase scheduled functions/etc.) is not yet built.
- **IMSLP terms** — ✅ confirmed; the connector is enabled (`IMSLP_ENABLED=1`).
- **YouTube `kind` via LLM** — the title heuristic misses plain performances/covers
  (many classify as `None`). Plan: classify with an LLM (a school-provided ChatGPT 5.5
  API key). Batch ~50–100 cards per call, each tagged with its card id, requiring a JSON
  array keyed by id back (so responses can't drift out of order); run as an offline async
  backfill (or the provider's Batch API). Not built yet.
- **Attribution residual** — `matching.py` cannot separate a piano cover of a piece from
  a *different* composition that shares the exact title (e.g. the Flight Facilities pop
  song "Clair de Lune"); both keep a high `match_score`. Conversely a real rendition
  titled by its parent work ("Suite bergamasque … Clair de lune") can score low.
  Separating these needs audio/semantic signal — future work.
- **IMSLP per-movement labeling** — disambiguation pages are now **resolved** to their
  real work pages (`enrich_cards`, Option A). Remaining nicety: a movement (e.g. Clair de
  lune) resolves to its **parent-work** page (Suite bergamasque, where it is track 3), so
  a "from {parent_work}" label / movement anchor would improve the UX. `parent_work` is
  already stored in `card.metadata`.
- **Recommender evaluation metric** — how exactly to score "is it recommending well"
  (precision@k / NDCG / AUC / …) is not yet decided. See §6 → Evaluation & data
  bootstrapping.
- **Training-data bootstrapping** — how to accumulate enough interaction data to train
  and evaluate: manual dogfooding vs. Claude-generated synthetic interactions. See §6.
- **`difficulty` usage** — how to measure and actually use difficulty (piece-level prior
  vs. per-rendition in `cards.metadata`) is unresolved; quarantined from the model until
  then. See §5 → `pieces`.
- **Ingest-by-channel / search-by-author** (potential next step) — browsing by creator is
  a feed filter over the existing `cards.author` (nearly free once the feed exists);
  optionally add a YouTube *by-channel* ingestion mode to pull a creator's whole catalog
  (e.g. the pianist "Birru"). Hard part: resolving a creator's freeform titles to piece
  slugs.
- **Composer sourcing beyond the search query** — `composer` is currently caller-supplied
  (the `--composer` arg), never derived from YouTube. Future options: IMSLP / MuseScore /
  Wikidata / MusicBrainz. IMSLP is authoritative but **classical-only**; pop/modern needs
  MusicBrainz / Wikidata / LLM (fuzzier, since pop "composer" = songwriter). *Partly
  addressed:* the IMSLP connector now parses composer from the page title into
  `card.author`; wiring that back to enrich `pieces.composer` during ingest is still open.

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
