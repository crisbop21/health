-- 005_workouts_natural_key.sql
-- Gives derived workout rows a stable identity so recompute can upsert
-- instead of delete-and-reinsert.
--
-- Before: every recompute deleted all garmin-sourced workouts and re-inserted
-- them — a crash mid-rebuild left the table empty, and the dashboard briefly
-- showed no workouts during every recompute. Now each row carries the source
-- record's id (garmin activityId / whoop workout id) and is upserted on
-- (source, external_id). This also enables the incremental nightly recompute
-- and Whoop workouts filling days Garmin didn't record.
--
-- Existing rows predate external_id, so we clear the table; it is derived and
-- fully rebuildable: after running this, press Settings -> Recompute metrics.
--
-- Idempotent: safe to run more than once. Run in the Supabase SQL editor.

alter table workouts add column if not exists external_id text;

delete from workouts;

create unique index if not exists uq_workouts_source_external
    on workouts (source, external_id);
