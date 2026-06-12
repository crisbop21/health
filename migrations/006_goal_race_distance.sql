-- 006_goal_race_distance.sql
-- The goal gains an explicit race distance so race-time projections can
-- compare "if race day were today" against the goal time at the right
-- distance (pace zones previously assumed marathon implicitly).
--
-- Existing goals default to the marathon distance, matching the prior
-- assumption. Idempotent: safe to run more than once. Run in the Supabase
-- SQL editor.

alter table goals add column if not exists race_distance_km numeric;

update goals set race_distance_km = 42.195 where race_distance_km is null;
