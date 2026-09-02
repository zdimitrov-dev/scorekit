# scorekit: project context

The design, current state and reasoning in one place. Keep it in sync with the code
(see [Keeping this file current](#keeping-this-file-current)).

**Last updated:** 2026-09-01
**Repo:** https://github.com/zdimitrov-dev/scorekit

---

## 1. Status

| Area | State |
|---|---|
| Repo, schema, Docker skeleton | Done. Schema applied to Supabase, RLS enabled on all tables |
| Source connectors | All three live: YouTube, IMSLP, MuseScore (via Tavily) |
| Corpus | ~580 pieces / 43 composers, seeded from IMSLP; grows with each search |
| Piano-only ingestion | YouTube filtered by `scorekit/piano.py`; IMSLP by instrument category |
| Attribution and enrichment | Match-scoring filter plus IMSLP work-page enrichment |
| Piece tagging | Derived from cards by `scorekit/tagging.py` |
| Feed UI | Next.js app in `web/`: masonry board, live search, card modal, more-like-this |
| Interaction logging | Impressions, opens, likes, saves, with dwell |
| Recommender (content-based) | Live. Ranks Home; signals still from localStorage |
| Learned ranker | Wired in behind a promotion gate. Held back: 19 of 40 positives |
| Dev dashboard | `/dev` in the web app and `GET /dev/stats`. Remove before release |
| Auth | Not started. Anonymous per-browser id stands in for a user |
| Docker image build | Not verified |

**Next action:** accumulate real interaction data until the learned ranker clears its gate
(40 likes or saves, section 8c). Until then compare it by hand with the "Try trained
model" toggle on Home or `python -m scorekit.jobs.compare`.

---

## 2. What scorekit is

A visual discovery platform for piano music. Users browse or search a board of cards,
where each card is a YouTube tutorial or performance, an IMSLP score, or a MuseScore
listing. A like/save system learns their taste and personalises a home feed.

**The problem.** Piano learners face a two-part gap no single tool covers: what to play
next is unguided, and finding the sheet music once decided is fragmented across three
sites that do not talk to each other.

**Two feed modes.** Search queries a specific piece and returns a mixed board from all
sources, ingesting the piece on demand if it is new. Home has no query and ranks the
corpus against accumulated like/save signal.

---

## 3. Architecture

- **Backend:** Python 3.13. Per-source ingestion jobs plus a FastAPI service
  (`scorekit/api.py`) the frontend calls.
- **Storage:** Supabase (managed Postgres).
- **Frontend:** Next.js App Router, Tailwind, framer-motion, in `web/`.
- **Containerisation:** Docker.
- **Deployment (Phase 7):** own subdomain, linked from the personal site.

### Pipeline

```
query
  -> each connector searches its source
  -> results normalised into Card objects
  -> YouTube results filtered to piano only
  -> attribution filter drops cards that are not the queried piece
  -> IMSLP enrichment and disambiguation resolution
  -> upsert piece (by slug) and cards
  -> derive piece_tags
  -> feed renders, interactions logged, recommender ranks Home
```

### API

| Endpoint | Purpose |
|---|---|
| `GET /search` | Blocking: all of a piece's cards at once |
| `GET /search/stream` | Streams cards per source as NDJSON so the UI rolls them out |
| `POST /recommend` | Ranks the corpus for one user's signals |
| `GET /similar` | Cards similar to one specific card |
| `POST /interactions` | Append interaction events |

---

## 4. Repository structure

```
scorekit/
  PROJECT_CONTEXT.md     this file
  AGENTS.md              agent guidance; CLAUDE.md points at it
  README.md              public-facing overview and setup
  db/
    schema.sql           full Postgres schema and RLS (idempotent)
    migrations/          incremental, idempotent SQL
  scorekit/
    config.py            env-backed Settings
    db.py                cached Supabase client
    models.py            Card, Piece, Interaction dataclasses
    normalize.py         normalize_slug: the cross-source dedupe key
    store.py             upserts, interaction logging, retagging
    matching.py          attribution scoring; drops cards that are not the piece
    piano.py             keeps YouTube results piano-only
    tagging.py           derives piece_tags from cards
    recommend.py         content-based ranker (serves Home)
    similar.py           more-like-this, ranked against one card
    api.py               FastAPI service
    connectors/          youtube.py, imslp.py, musescore.py, base.py
    ml/                  learned ranker: features.py, dataset.py, train.py,
                         registry.py (promotion gate), serve.py (scoring)
    jobs/                ingest, seed, tag_pieces, migrate, purge, simulate,
                         train_model, compare, stats
  models/                the saved ranker, gitignored
  tests/                 one module per area
  web/                   Next.js app
```

---

## 5. Data model

Defined in `db/schema.sql`; mirrored by dataclasses in `scorekit/models.py`.

### The core idea: separate what from how

A piano recommender answers two different questions that need different data.

1. *Does this user like this piece?* Taste and content: composer, era, form. Lives in
   `pieces` and `piece_tags`.
2. *Does this user like this presentation?* Format: tutorial vs performance, YouTube vs
   score, which channel. Lives in `cards` (`source`, `kind`, `author`).

`interactions` ties a user to both at once, so a preference can be decomposed into
taste-for-piece times taste-for-format. That yields far more signal per interaction,
which matters while data is sparse.

### `pieces`

`id, slug (unique), title, composer, era, genre, difficulty, created_at, updated_at`

- `slug` is the normalised key (`debussy-clair-de-lune`). It makes a like on a YouTube
  video and a like on the IMSLP score of the same piece roll up to one `piece_id`.
  Data efficiency is bounded by normaliser quality: a miss fragments a user's signal.
- `composer`, `era`, `genre` are content features and the basis for cold-start
  recommendations, so a brand-new piece is rankable immediately.
- **`difficulty` is quarantined.** It stays in the schema but nothing in the recommender
  may depend on it yet. It is hard to measure, and it is really a property of the
  *rendition* rather than the piece: a simplified arrangement of La Campanella and the
  original differ enormously. At most a coarse piece-level prior; per-rendition
  difficulty belongs in `cards.metadata`.

### `cards`

`id, piece_id (cascade), source, kind, external_id, url, title, thumbnail_url, author,
metadata (jsonb), created_at, unique(source, external_id)`

- `source` and `kind` are low-cardinality categorical presentation features.
- `author` (channel or arranger) is higher-cardinality and needs embeddings or target
  encoding to use properly.
- `metadata` is the escape hatch for source-specific fields: view count, duration,
  match score, matcher version, ingest rank.
- **Cards from different sources are never merged** into one grouped result. Each stays
  its own card; normalisation happens quietly through `piece_id`.

### `interactions`

`id, user_id, card_id (set null), piece_id (set null), action, dwell_ms, feed_position,
created_at`

- **Both `card_id` and `piece_id` are stored.** `piece_id` is derivable, but denormalising
  it gives cheap training queries and signal durability: if a video is deleted `card_id`
  goes null while "user liked that Chopin piece" survives.
- **`action` is graded, not boolean:** `like` and `save` are explicit positives, `click`
  is positive when dwell is long, `impression` is the implicit negative, `skip` reserved
  for an explicit reject control that does not exist yet.
- **`dwell_ms`** weights confidence in the label rather than being a feature: it is only
  observable after a card is shown, so using it as a feature would leak.
- **`feed_position`** is stored for position-bias correction and deliberately unused by
  the first-pass model.

> Do not clear the `cards` table once real interactions exist. `card_id` is
> `on delete set null`, so wiping the corpus keeps the events but severs them from the
> features they describe.

### `piece_tags`

`piece_id (cascade), key, value, primary key (piece_id, key, value)`

Entity-attribute-value, so a piece can hold several values of the same key and new
feature types need no migration. `idx_piece_tags_kv(key, value)` powers reverse lookup
("all romantic pieces"), which is candidate generation for content-based recommendations.

---

## 6. Ingestion

### 6a. Corpus seeding (`scorekit/jobs/seed.py`)

Ingestion is otherwise reactive: nothing enters the database until someone searches for
it, so the corpus mirrors previous searches. That caps the recommender twice. It can
never surprise anyone with a piece nobody looked up, and on a tiny corpus the IDF
statistics it weights tags by are computed from noise. Neither is fixed by more
interactions; both need more items. Seeding took the corpus from 18 pieces to 580.

IMSLP is the right source: no API quota, page titles carry the composer, and work pages
carry style and instrumentation, so pieces are rankable on arrival. Only IMSLP cards are
created; video and MuseScore hydration stays lazy.

Which categories count as piano was measured, and the obvious answer is wrong in both
directions (`connectors/imslp.PIANO_CATEGORIES`):

- `For piano` alone collapses the baroque, because IMSLP files music by the instrument it
  was written for. Bach has 1 work in it, Scarlatti 0, Handel 2. Adding `For keyboard`
  and `For harpsichord` fixes it (Bach 277, Scarlatti 558) at no cost.
- Adding `For piano (arr)` would nearly double Mozart and Beethoven with piano reductions
  of symphonies, and admits works like Chopin's Cello Sonata.

Seeding is composer-scoped and priority-ordered: `Category:For piano` holds 54,000+ pages
alphabetically, so a small per-composer cap would otherwise seed the obscure end of every
composer. Naming a musical form and carrying an opus number both track how well known a
work is.

### 6b. Piano-only YouTube (`scorekit/piano.py`)

YouTube search is not a piano index. "Rousseau" returns political philosophy alongside
that pianist's covers, and anything let through lands in the corpus permanently. IMSLP is
filtered by instrument category and MuseScore returns sheet music by construction, so only
YouTube needs this.

Keyword matching fails in both directions:

- "Chopin - Nocturne op.9 No.2" never says *piano*, in title or description.
- Kassia's "Beethoven - Symphony No. 5" is a Liszt piano transcription, while the
  identically-titled DW Classical upload is an orchestra.

So the rules are layered. Piano evidence is read from everywhere including the
description and checked first, so a transcription survives its own title. Rejection reads
the title and channel only, because a pianist's bio naming the orchestras he plays with
was dropping his solo Grieg. Results silent either way fall back to whether the piece is
piano repertoire. A channel the result set has already shown to be a piano channel vouches
for its others.

Measured live: 10 of 12 piano queries keep 100% of results; the only drops on the other
two are a saxophone quartet and a Coldplay live set. Taylor Swift, gaming laptops, tyre
changes and a violin concerto all go to zero.

### 6c. Attribution (`scorekit/matching.py`)

Scores each card against what was searched for and drops clear non-matches
(`DROP_THRESHOLD`, lenient, so related works survive at a lower score).

- **Title:** blends token overlap with the longest contiguous run, the latter weighted
  higher because word order carries the phrase.
- **Author:** an all-or-nothing escape hatch for queries naming an artist rather than a
  piece, since their video titles never contain their own name. Every query token must
  appear in the author in order, as a whole token or the start of one, so shortened names
  work ("Kat Cordova" names Katherine Cordova) without a partial overlap rescuing a card
  the title rejected.
- **Numbers** are handled by contradiction, not absence: a card naming a different opus is
  penalised hard, one naming no number at all only nudged.

`annotate_and_filter` also records each card's `rank` (the connector's own relevance
position) and `mv` (`MATCHER_VERSION`).

### 6d. Search caching (`api._ingest_stream`)

Cache per source on actual cards, never on the existence of the piece row. A piece whose
ingest stored nothing would otherwise be a permanent negative cache, replaying zero cards
and reporting "no results" forever for a query that once worked.

Cards also carry `metadata.mv`. A source scored by superseded matching is re-ingested
rather than replayed, because dropped cards are never stored: a scoring fix cannot be
applied by re-scoring the database, only by re-fetching. Bump `MATCHER_VERSION` whenever
scoring changes which cards are kept.

---

## 7. Tagging (`scorekit/tagging.py`)

Tags are derived at the piece level because enrichment is uneven: a YouTube card knows
almost nothing about the music, while one IMSLP card carries style, instrumentation and
licensing. Since every card for the same piece shares a `piece_id`, one enriched card
makes the whole piece rankable.

Keys produced: `composer`, `era`, `style`, `instrumentation`, `form`, `format`, `creator`,
`public_domain`.

Three rules keep the tags honest, each added after a real failure:

- **Only high-confidence cards define a piece.** The attribution filter deliberately keeps
  loosely-related neighbours, but those must not describe the piece: deriving from every
  card tagged Debussy's "Clair de lune" a rag.
- **A value needs corroboration.** One ragtime cover should not make the work a rag; one
  orchestral transcription should not make "Fur Elise" orchestral.
- **Composer is voted, not taken from one source.** IMSLP's `author` is authoritative for
  an original work but names the arranger on a derivative, which made "Moonlight Sonata"
  come out as the composer of a guitar transcription. Votes from card titles and IMSLP
  authors are merged and a name needs two.

`format` (tutorial / cover / performance) is what a piece's cards mostly are. It is a real
taste dimension and the only feature a non-classical entry may have: a "Coldplay piano"
search had 45 cards and zero tags without it. `creator` does the same for artist searches,
where a dominant channel is what the entry is about.

Tagging runs at ingest, not only as a batch job: a piece ingested but never tagged has zero
affinity and is invisible to the recommender.

---

## 8. Recommender

### 8a. Content-based, serving Home (`scorekit/recommend.py`)

Four steps: profile, score, blend, diversify.

- **Profile.** Liked and saved pieces become a weighted tag vector. `save` (1.5) outweighs
  `like` (1.0); `skip` is negative. L2-normalised so a heavy user is compared on the same
  scale as a new one.
- **Score.** Tag affinity weighted by IDF times `KEY_WEIGHTS`. IDF measures rarity;
  `KEY_WEIGHTS` measures what a kind of tag says about taste, and the two are not the
  same. Sharing a composer means far more than sharing an instrument, and in piano
  repertoire almost everything involves a piano. With IDF alone, a heterogeneous entry
  that had accumulated many incidental tags matched every profile through low-information
  overlap and outranked genuine neighbours.
- **Blend.** Affinity and popularity are min-maxed across the candidate pool before
  blending, or `POPULARITY_WEIGHT` is not a real proportion. Raw cosine between two
  genuinely related pieces is about 0.15 however related they are, while any popular video
  sits at 0.75 to 0.85 popularity, so blending directly let popularity outweigh the best
  possible tag match.
- **Diversify.** Repeats fade multiplicatively, plus a hard ceiling on consecutive cards
  from one piece. A flat penalty was wrong in both directions: large enough to prevent a
  wall drove the second card of a liked piece to zero, small enough to avoid that let one
  piece own the board.
- **Engaged cards are held back, not their pieces.** Excluding the piece meant liking a
  Liszt etude removed every Liszt card from the feed.

Verified end to end: searching Grieg, liking four results, then opening Home gives a board
whose top three cards are all Grieg, followed by romantic neighbours.

**Known cleanup, deliberately not done.** `_popularity` returns 0.0 when a card has no
`view_count`, conflating "unmeasurable" with "unpopular"; IMSLP and MuseScore have no view
metric so they sort last. The blast radius is one state: with zero signals, affinity
rescales to all-zero and popularity becomes the whole ranking, so a user who has liked
nothing sees 18 of 580 pieces. One like self-corrects it to 42 of 80. Fixing it means
treating missing popularity as neutral, which flips cold-start Home to a board dominated
by seeded IMSLP pieces, only 65% of which have a thumbnail.

### 8b. More like this (`scorekit/similar.py`)

Ranks against the single card being viewed, not the user's taste, so it works on the first
click and cannot pull the home feed around. Similarity is tag overlap plus title-word
overlap, because tags cannot express what a performer covers: "Birru playing Laufey" and a
Laufey recording share no tag at all. Cards sharing neither are dropped rather than ranked
low. The strip logs no impressions: browsing one card's neighbours is exploring, not
rejecting.

### 8c. Learned ranker (`scorekit/ml/`, wired in behind a gate)

`scorekit/ml/` plus `jobs/train_model.py`. Sits beside the content ranker rather than
replacing it, so the hand-tuned weights and the learned ones can be compared head to head
on the same held-out rows.

**Features are crossed with the user's history.** Not "is this Chopin" but "how far does
this piece overlap your history on the composer axis". Raw tags would need one column per
composer, and with 43 composers each column carries two or three examples. Each tag kind
gets its own axis, so the model derives how much composer matters relative to
instrumentation instead of being told by `KEY_WEIGHTS`. Missing view counts are NaN rather
than 0, so trees branch on missingness instead of being lied to.

**Labels.** `like`, `save` and long `click` are positives; `impression` and short clicks
are negatives. Dwell weights the example, and those weights are passed to `fit` (they were
computed and discarded until 2026-09-01, which quietly disabled the whole mechanism).

**Hyperparameters are searched, not guessed** (`train.tune_forest`, `--tune`). A randomised
cross-validated search over depth, leaf size and feature sampling, run **inside the training
split only** — choosing hyperparameters against the test rows would make the reported score
a description of the search rather than of the model. It declines to run when the training
split holds fewer than three positives. On the current log it picks `max_depth=3` over the
hand-picked 6, which is the forest being reined in from overfitting 12 positives.

**Synthetic rows cannot promote a model.** `jobs/simulate` writes under deterministic UUIDs
(`simulate.simulated_user_ids`), and `train_model` excludes them unless asked; `--simulated
only` trains on them alone, which is how the forest is demonstrated against a known taste.

**Two methodology traps, both handled.** A user's profile is built only from their earlier
events, so it can never contain the label being predicted. And splitting is per user: a
pooled 70/30 cut put every test row inside a single user, because rows are grouped by user,
silently measuring cross-user generalisation while claiming to measure next-behaviour
prediction. Both modes are reported.

Results on simulated personas. `jobs/simulate.py` writes interactions from a written-down
taste, which is the only way to judge a ranker before there is traffic: with real logs
there is no ground truth, only a metric that may be high for the wrong reasons. Twelve
personas, some deliberately overlapping, 500 events each spread over twenty days, with a
like rate near one in ten so an easy class balance does not flatter every metric.

| model | AUC, same users | 95% interval | AUC, held-out users |
|---|---|---|---|
| random forest | **0.857** | 0.810 to 0.900 | **0.862** |
| random forest (tuned) | 0.851 | 0.805 to 0.891 | 0.856 |
| xgboost | 0.849 | 0.802 to 0.893 | 0.845 |
| logistic regression | 0.825 | 0.775 to 0.873 | 0.841 |
| heuristic (tag affinity) | 0.807 | | 0.828 |

Intervals are bootstrapped over the 1,230 held-out rows, 2,000 resamples. **The top
three are tied.** Reading an ordering between them is reading noise: tuned minus
untuned is -0.006, interval -0.069 to +0.055, straddling zero comfortably.

That the tuned forest does not beat the untuned one is not a failure of tuning. A
search optimises the *cross-validation estimate* on the training split, and with about
48 positives per fold that estimate is noisy, so taking the maximum over 40 candidates
partly takes noise. Tuning buys robustness when the defaults are badly wrong and buys
nothing measurable when they are already reasonable. It stays because it is the honest
way to choose settings, not because it always wins.

Random Forest is the best model in both modes, and beats XGBoost in both, which is why
several models are fitted rather than assuming boosting wins on tabular data.

**The gate declines it anyway**, and that is the result worth reading. The margin over the
heuristic is +0.017 on the split promotion is judged on, well under the 0.03 required. The
reason is visible in the importances: the forest's top features are `affinity_overall`,
`seen_composer_before` and `affinity_composer` — nearly the same information the heuristic
already uses. What the model adds is learning the relative weight of each axis instead of
being handed `KEY_WEIGHTS`, and that is worth about two points of AUC, not ten.

**Did it recover the taste we wrote down?** (`jobs/recover.py`) Every other number here is
computed against behaviour, which is what the model was fitted on, so a high score can come
from learning the taste or from learning an artefact of collection and look identical either
way — the fabricated-timestamp model scored 0.914, better than anything honest has. Personas
are the one case where that ambiguity is escapable: their preferences exist as numbers the
model never sees. Ranking the whole corpus for each and scoring the top ten against those
numbers, scaled so 0% is a random ordering and 100% is the best any ranking could achieve:

| | mean over 16 personas |
|---|---|
| heuristic (tag affinity) | **87%** |
| learned model | 81% |

**The two measurements disagree, and that is the most useful thing here.** The model
wins decisively on held-out engagement and loses on recovering the taste.

The reason is that the answer key is written in the baseline's own vocabulary. Recovery
scores a ranking against the persona's *tag* weights, and the baseline ranks on nothing
but tag match, so the two speak the same language. The model predicts engagement from
22 features, 13 of which describe the card rather than the taste: view count, duration,
source, kind. In the simulator none of those affect whether a persona likes something,
so any weight placed on them is a straight loss here. The model is penalised for using
all the evidence available in a world where most of it is irrelevant by construction.

Worth stating rather than filing under distribution shift, which was the first guess
and was wrong: the simulator draws uniformly, so every card appears in training and the
model is not extrapolating anywhere.

It is also not uniform. The model takes `romantic-pianist` 100% to 59% and loses
`romantic-sonatas-classical-miniatures` 15% to 100%; excluding that one persona the
means are 85% and 86%. A simpler "does the top ten contain any tag this persona wants"
measure is reported alongside and is useless, since every ranker scores 100% when a
persona wanting "romantic" matches 274 of 582 pieces. Kept to show why the scaled
measure is the one to read.

**`feed_position` was tried and is off by default** (`--with-position`). Two findings, and
the second matters more than the first.

It did not help. Measured on the earlier purely-linear personas, before the interaction
ones existed: forest 0.837 to 0.833 chronological, 0.866 to 0.860 cross-user, with
precision@10 falling from 0.60 to 0.40. But that is not evidence against position bias.
`jobs/simulate` assigns position with `rng.sample` and its like probability depends only on
tags, so the synthetic data contains no position effect to find. The column is noise there,
and an extra noise column costs a little accuracy. The test was fair to the feature and
uninformative about the phenomenon.

It also cannot be served. At training time the position is known; at ranking time it does
not exist, because the scores are what decide it. `ml/serve` therefore refuses a model
whose feature list contains it, rather than quietly feeding NaN into a column the model was
told to trust and looking like a model that never helps.

The usual correction is inverse propensity weighting: weight each row by the inverse
probability that a card at that rank was examined at all, so a like from the bottom of the
feed counts for more than one from the top. **Deliberately not done, and not a TODO.** It
could only be validated against a simulator, and a simulator has no attention to draw down
a page. Any decay curve would be one we invented, so measuring the correction against it
would only confirm we can undo our own assumption. Position bias is real in real traffic
and is the right thing to reach for once there is some; it is not a thing synthetic data
can answer.

**Promotion gate (`ml/registry.py`).** A fit is not automatically worth serving. On a small
or skewed log it can rank worse than the heuristic and worse than chance, and promoting it
would degrade the feed with nothing to indicate why. A fit only serves once it clears
`MIN_POSITIVES = 40` likes or saves, beats chance, and beats the heuristic by
`MIN_AUC_GAIN = 0.03` on the chronological split. Until then `/recommend` keeps the content
ranker, which is the correct outcome rather than a failure.

**Where it plugs in (`ml/serve.py`).** The model supplies the relevance term only; the
popularity blend, diversity pass and already-engaged rules in `recommend` are untouched. So
falling back changes exactly one input and nothing else. `score_cards` returns `None` when
there is no model, when it is unpromoted, when the user has no history, or on any
exception, so every failure path lands on the heuristic.

**Testing a fit that has not been promoted.** `train_model --force` saves it marked
`passed_gate: false`. It is never used on its own, but it can be asked for by name:

- `POST /recommend {"ranker": "model"}` and the "Try trained model" toggle on Home serve it
  to that one request.
- `jobs/compare.py` prints heuristic and model side by side over the same corpus and
  history, since one list alone cannot say whether a ranker is better.
- `GET /dev/stats` and `/dev` in the web app report which ranker is live, the gate reason,
  the scores, and how far the interaction log is from the threshold.

**Current standing on real data:** logistic AUC 0.579, heuristic 0.407, 19 positives. The
gate declines on the positives count alone. That heuristic figure is confounded, not an
indictment of the feed: the negatives are impressions from the heuristic's own ranking, so
it is being asked to separate likes from scroll-pasts among items it already judged alike.

Note that personalisation already adapts without retraining: because features are crossed
with history, a new like changes the ranking on the next page load. What is frozen is how
much each axis is worth.

---

## 9. Interaction logging (`web/lib/track.ts`, `POST /interactions`)

The dataset the learned ranker trains on. Identity is an anonymous per-browser UUID: no
account, no personal data, replaceable by a real user id when auth lands. It must be a
UUID, because `interactions.user_id` is a uuid column and anything else makes Postgres
reject the whole batch.

Negatives come from impressions, since the feed has no reject control. Quality of that
signal took three fixes, each found by inspecting what actually landed in the table:

- **Visibility, not rendering.** At least half visible for at least 900ms, so a card that
  flew past during a fast scroll is not recorded as considered-and-rejected.
- **Dwell measured on exit, not at the threshold.** Logging when the card first qualified
  made every row report the same ~900ms, so the column carried no information.
- **A settle timer.** A card that never leaves the viewport was never recorded, so the top
  of the feed was the least logged. Cards still visible after 8s are written then, which
  right-censors those values.
- **Timestamps say when it happened, not when it was written.** `created_at` defaults to
  `now()`, which is a batch interval late for an ordinary event and arbitrarily late for
  anything flushed at page exit or recovered by a reconciliation. The client now stamps
  `occurred_at` and the server stores it, within a sanity window so a wrong client clock
  cannot reorder a history. This matters because the chronological split and the
  profile-leakage guard both read `created_at` as truth. Two traps here: a batch mixing
  rows with and without a timestamp gets sent explicit NULLs by PostgREST and is rejected
  whole, so gaps are filled before insert; and likes recorded before the browser started
  keeping times cannot be recovered at all, which is what `backfilled` marks.
- **A second bar, applied at training time.** 0.9s of visibility is cheap on a three-column
  board: a steady scroll clears it on nearly every card, so most impressions were cards
  never actually looked at, and the negative class had no consistent meaning. The browser
  still logs at 0.9s, but `dataset.MIN_IMPRESSION_MS` discards anything under 1.8s when
  building training rows. Filtering here rather than in the client keeps the raw log intact
  and applies to rows already stored. Confidence then ramps with time on screen (0.25 at
  the bar to 1.0 at 8s) instead of stepping.

Sub-400ms modal opens are discarded as mis-clicks. Events batch and flush via `sendBeacon`
on the way out, since `fetch` is cancelled at unload. All failures are swallowed: this is
telemetry, and may cost training data but never the user's action.

**Open issue.** Impressions outnumber positives roughly 30 to 1, and a half-second glance
weighs nearly the same as a considered look. Planned fix: raise the visibility bar and
grade the negative's weight smoothly by time on screen. Weighting is applied at training
time, so it can be corrected retroactively.

---

## 10. Frontend notes (`web/`)

Reads Supabase server-side with the service key; no secret reaches the browser.

- **Masonry uses explicit columns, not CSS `columns-*`,** which re-flows its whole content
  on append and made "Load more" reshuffle the board. Each card is placed into the
  measurably shortest column once and never moves. A fresh list places from zero heights,
  because the reset has not painted and the DOM still holds the previous board.
- `Feed` identifies its list by a signature of card ids, never array identity. Callers
  build those arrays during render, so the reference changes on every parent re-render,
  including the one caused by opening a card. Keying on identity wiped the board on click
  and unmounted the card mid-transition.
- **Video cards take one of a few crop shapes** chosen from the card id. Every YouTube
  thumbnail is 16:9, so a board of them measured as every card exactly 272px tall: a grid,
  not masonry. Score images keep their natural portrait shape.
- **Home reads a ranking prepared in advance** (`lib/feedCache.ts`), built on app load and
  rebuilt the moment a like or save lands, keyed by a signature of the signals it came
  from. Ranking depends on browser-held history, so it can never be server-rendered
  correctly; previously Home painted a server board and re-sorted it a second later.
- **The Saved tab fetches saved cards by id.** It used to pull a capped slice of the corpus
  and filter it down, silently dropping anything saved outside the cap.
- **The recent-searches panel opens on click, not focus.** The input autofocuses, so
  opening on focus covered the top row of results and swallowed clicks meant for them.

---

## 11. Roadmap

| Phase | Scope | State |
|---|---|---|
| 0 | Repo, schema, Docker skeleton | Done |
| 1 | YouTube connector | Done |
| 2 | IMSLP connector, enrichment, disambiguation | Done |
| 3 | MuseScore via Tavily | Done |
| 4 | Feed UI, live search, corpus seeding | Done |
| 5 | Interaction logging | Done |
| 6 | Recommendation engine | Content-based live; learned ranker gated on data volume |
| 7 | Polish and deploy | Not started |

---

## 12. Local setup

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
npm install && npm run dev        # API on :8000, web on :3210
```

`web/.env.local` holds `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` for the frontend.

Environment variables: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_DB_URL`
(migrations only, must point at the connection pooler), `YOUTUBE_API_KEY`,
`TAVILY_API_KEY`, `IMSLP_ENABLED`.

Restart the stack after backend changes. `uvicorn --reload` is unreliable here: a reload
worker can survive its parent and keep serving stale code on the port.

---

## 13. Conventions

- **Commit locally, do not push.** The maintainer reviews and pushes.
- **Commit style:** concise imperative subject; body explains the why when not obvious.
- **Secrets only in `.env`** (gitignored). Never send the service-role key to the browser.
- **No emoji** in code, comments or documentation.

---

## 14. Open questions

- **Query normalisation.** A freeform query is slugged as-is, so "Clair de Lune" and
  "Debussy Clair de Lune" become different pieces, and "kat-cordova" and
  "katherine-cordova" are duplicates of one channel. Composer parsing or fuzzy matching
  would unify them.
- **Auth and a `users` table.** Likes and saves live in `localStorage`;
  `interactions.user_id` is a bare uuid. Both need wiring to Supabase auth.
- **RLS policies.** All four tables have RLS enabled with no policies, so only the service
  key can read. Correct today, real work once the browser reads its own rows.
- **Position bias.** Real in real traffic, unanswerable with synthetic users (see 8c).
  Revisit when the log has traffic from more than one person.

- **Cold-start popularity.** The conflation described in 8a.
- **YouTube `kind` via an LLM.** The title heuristic classifies many cards as `None`.
  Batch 50 to 100 cards per call, keyed by card id so responses cannot drift out of order.
- **Attribution residual.** `matching.py` cannot separate a piano cover from a different
  composition sharing the exact title. Separating them needs audio or semantic signal.
- **IMSLP per-movement labelling.** A movement resolves to its parent-work page, so a
  "from {parent_work}" label would help. `parent_work` is already stored.
- **Source diversity in the feed.** High-view YouTube cards cluster ahead of score cards.
- **`difficulty`.** How to measure it, and whether it belongs on the piece or the card.
- **Scheduling.** Ingestion and seeding are CLI jobs; nothing runs them automatically.
- **Docker image.** Structurally complete, never built or verified.

---

## 15. External resources

- scorekit repo: https://github.com/zdimitrov-dev/scorekit
- Personal site repo: https://github.com/zdimitrov-dev/personalweb
- Supabase dashboard: https://supabase.com/dashboard

---

## Keeping this file current

This document is the project's source of truth. Update the status table when something
moves from stub to built, the roadmap when a phase starts or finishes, open questions as
they resolve, and the date at the top. If something here no longer matches the code, fix
it. Record the reasoning behind a decision, not the narrative of how it was reached.
