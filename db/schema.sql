-- scorekit schema (Phase 0)
-- Apply with: psql "$SUPABASE_DB_URL" -f db/schema.sql
--
-- Design principle: cards from different sources are never merged into a single
-- grouped result. Each result is its own card. Normalization happens quietly via
-- a shared piece_id so the recommender can attribute signal across sources.

-- gen_random_uuid() is available in Postgres 13+ (and on Supabase) out of the box.

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
do $$ begin
  create type card_source as enum ('youtube', 'imslp', 'musescore');
exception when duplicate_object then null; end $$;

do $$ begin
  create type card_kind as enum ('tutorial', 'cover', 'performance', 'score', 'listing');
exception when duplicate_object then null; end $$;

do $$ begin
  create type interaction_action as enum ('like', 'skip', 'click');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- pieces: canonical entity per real piece
-- ---------------------------------------------------------------------------
create table if not exists pieces (
  id          uuid primary key default gen_random_uuid(),
  slug        text unique not null,          -- normalized dedupe key (composer + title)
  title       text not null,
  composer    text,
  era         text,                          -- baroque, classical, romantic, modern, ...
  genre       text,
  difficulty  smallint,                      -- 1..10, nullable until known
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- cards: one row per individual result (video, score, listing) -> what renders
-- ---------------------------------------------------------------------------
create table if not exists cards (
  id            uuid primary key default gen_random_uuid(),
  piece_id      uuid not null references pieces(id) on delete cascade,
  source        card_source not null,
  kind          card_kind,
  external_id   text not null,               -- provider id (video id, imslp page, url hash)
  url           text not null,
  title         text,
  thumbnail_url text,
  author        text,                        -- channel / uploader / arranger
  metadata      jsonb not null default '{}', -- source-specific extra fields
  created_at    timestamptz not null default now(),
  unique (source, external_id)
);

-- ---------------------------------------------------------------------------
-- interactions: training signal for the recommender
-- ---------------------------------------------------------------------------
create table if not exists interactions (
  id          bigint generated always as identity primary key,
  user_id     uuid not null,
  card_id     uuid references cards(id) on delete set null,
  piece_id    uuid references pieces(id) on delete set null,
  action      interaction_action not null,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- piece_tags: features the recommender learns over
-- ---------------------------------------------------------------------------
create table if not exists piece_tags (
  piece_id  uuid not null references pieces(id) on delete cascade,
  key       text not null,                   -- 'composer', 'era', 'mood', 'difficulty', ...
  value     text not null,
  primary key (piece_id, key, value)
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
create index if not exists idx_cards_piece         on cards(piece_id);
create index if not exists idx_interactions_user   on interactions(user_id, created_at desc);
create index if not exists idx_interactions_piece  on interactions(piece_id);
create index if not exists idx_piece_tags_kv       on piece_tags(key, value);
