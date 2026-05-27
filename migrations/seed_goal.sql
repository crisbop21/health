-- seed_goal.sql
-- One active goal for Phase 1: a December 2026 marathon, 4:00:00 target.
-- Run once in the Supabase SQL editor after 001_initial_schema.sql.

update goals set active = false where active;

insert into goals (
    sport, race_date, goal_time_seconds, days_per_week,
    max_session_minutes, time_windows, blackout_dates, active
) values (
    'running',
    '2026-12-06',
    14400,                                   -- 4h00m00s
    5,
    120,
    '{"default": ["06:00", "08:00"]}'::jsonb,
    '[]'::jsonb,
    true
);
