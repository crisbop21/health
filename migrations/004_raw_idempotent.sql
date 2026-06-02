-- 004_raw_idempotent.sql
-- Makes device ingestion idempotent so re-syncing the same days stops piling up
-- duplicate rows (and, via recompute, duplicate workouts).
--
-- Before: every sync inserted a fresh garmin_raw / whoop_raw row, even for data
-- already stored. Now each logical record carries a stable external_id and is
-- upserted on (endpoint, external_id):
--   garmin daily_stats -> external_id = the day
--   garmin activities  -> external_id = activityId   (one row per activity)
--   whoop  records     -> external_id = id / cycle_id (one row per record)
--
-- The existing rows predate external_id and are full of duplicates, so we clear
-- both raw tables. They are fully re-fetchable: after running this migration,
-- re-run Settings -> Backfill, then Recompute metrics. Derived tables
-- (daily_metrics, workouts) are untouched until you recompute.
--
-- Idempotent: safe to run more than once. Run in the Supabase SQL editor.

alter table garmin_raw add column if not exists external_id text;
alter table whoop_raw  add column if not exists external_id text;

delete from garmin_raw;
delete from whoop_raw;

create unique index if not exists uq_garmin_raw_endpoint_external
    on garmin_raw (endpoint, external_id);
create unique index if not exists uq_whoop_raw_endpoint_external
    on whoop_raw (endpoint, external_id);
