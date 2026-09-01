-- 002: mark interaction rows whose timestamp is not when the action happened.
--
-- POST /interactions/sync reconciles likes and saves this browser holds that the log is
-- missing, which is how the two stores converge after an outage. The likes are genuine,
-- but the row is written now rather than when the person pressed the button, so every
-- backfilled row lands at the same instant.
--
-- That matters because evaluation is chronological: the model is trained on a user's past
-- and tested on their future, and a user's taste profile is built only from their earlier
-- events. A block of likes sharing one timestamp breaks both. Rows late in the block get a
-- profile holding dozens of near-identical likes and become trivially predictable, which
-- inflates held-out AUC without the model having learned anything.
--
-- Flagged rather than dropped: the like is real evidence of taste and should still seed a
-- profile. It just cannot be a labelled row in a time-ordered evaluation.
--
-- Apply with:  python -m scorekit.jobs.migrate
-- (or paste into the Supabase SQL editor)
alter table interactions
  add column if not exists backfilled boolean not null default false;

comment on column interactions.backfilled is
  'True when the row was reconciled from a client rather than logged as it happened, so '
  'created_at is the sync time and carries no ordering information.';
