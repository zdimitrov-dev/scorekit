-- Phase 5: widen interaction_action, and index the training-set read path.
--
-- Additive only — no existing rows or columns are touched, and the app runs correctly
-- without this. Logging maps onto the original three actions today (see store.log_events):
-- a seen-but-unengaged card is written as `skip`, which is exactly what the schema's own
-- notes describe as the negative signal. Applying this migration unlocks two refinements:
--
--   impression : separates "seen and passed over" from a deliberate reject, so the two
--                can be weighted differently once an explicit skip control exists.
--   save       : distinct from `like` because saving is a deliberate "keep this" and
--                carries more weight (see recommend.SIGNAL_WEIGHTS). Merged into `like`
--                until this runs.
--
-- Apply with:  python -m scorekit.jobs.migrate
-- (needs SUPABASE_DB_URL pointing at the connection *pooler*; the legacy
--  db.<ref>.supabase.co host no longer resolves over IPv4. Pasting this file into the
--  Supabase SQL editor works just as well.)
do $$ begin
  alter type interaction_action add value if not exists 'impression';
exception when others then null; end $$;

do $$ begin
  alter type interaction_action add value if not exists 'save';
exception when others then null; end $$;

-- An impression is logged for every card seen, so this table becomes by far the largest
-- in the schema. This index is what keeps "all of one user's history" cheap to read when
-- assembling a training set.
create index if not exists idx_interactions_user_card
  on interactions(user_id, card_id);
