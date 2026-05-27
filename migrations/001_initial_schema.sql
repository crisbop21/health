-- 001_initial_schema.sql
-- Personal Health and Training Assistant - initial schema (all 10 tables).
-- Run in the Supabase SQL editor. Raw payload tables are kept indefinitely;
-- derived tables (daily_metrics, workouts) can be recomputed by replaying raw.

create extension if not exists pgcrypto;

-- 1. Configurable goal. A new active row is written on each edit; the previous
-- active row is set active=false so history is preserved.
create table if not exists goals (
    id                  uuid primary key default gen_random_uuid(),
    sport               text not null default 'running',
    race_date           date not null,
    goal_time_seconds   integer,
    days_per_week       integer,
    max_session_minutes integer,
    time_windows        jsonb not null default '{}'::jsonb,
    blackout_dates      jsonb not null default '[]'::jsonb,
    active              boolean not null default true,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);
create index if not exists idx_goals_active on goals (active) where active;

-- 2. Raw Garmin payloads, never parsed in place.
create table if not exists garmin_raw (
    id          uuid primary key default gen_random_uuid(),
    recorded_at timestamptz,
    endpoint    text not null,
    payload     jsonb not null,
    ingested_at timestamptz not null default now()
);
create index if not exists idx_garmin_raw_recorded_at on garmin_raw (recorded_at);
create index if not exists idx_garmin_raw_endpoint on garmin_raw (endpoint);

-- 3. Raw Whoop payloads.
create table if not exists whoop_raw (
    id          uuid primary key default gen_random_uuid(),
    recorded_at timestamptz,
    endpoint    text not null,
    payload     jsonb not null,
    ingested_at timestamptz not null default now()
);
create index if not exists idx_whoop_raw_recorded_at on whoop_raw (recorded_at);
create index if not exists idx_whoop_raw_endpoint on whoop_raw (endpoint);

-- 4. Derived, source-resolved daily metrics (Whoop wins HRV/recovery/sleep).
create table if not exists daily_metrics (
    id             uuid primary key default gen_random_uuid(),
    date           date not null unique,
    hrv_ms         numeric,
    resting_hr     numeric,
    sleep_hours    numeric,
    recovery_score numeric,
    strain         numeric,
    source_hrv     text,
    source_sleep   text,
    computed_at    timestamptz not null default now()
);
create index if not exists idx_daily_metrics_date on daily_metrics (date);

-- 5. Derived workouts (Garmin wins; manual fallback possible).
create table if not exists workouts (
    id               uuid primary key default gen_random_uuid(),
    date             date not null,
    sport            text,
    distance_km      numeric,
    duration_seconds integer,
    avg_pace         text,
    avg_hr           numeric,
    max_hr           numeric,
    source           text,
    raw_id           uuid references garmin_raw (id)
);
create index if not exists idx_workouts_date on workouts (date);

-- 6. Generated training plan, one row per planned day per version.
create table if not exists training_plan (
    id                       uuid primary key default gen_random_uuid(),
    date                     date not null,
    planned_sport            text,
    planned_workout_type     text,
    planned_distance_km      numeric,
    planned_duration_minutes integer,
    planned_pace             text,
    intensity_zone           text,
    notes                    text,
    version                  integer not null default 1,
    generated_at             timestamptz not null default now()
);
create index if not exists idx_training_plan_date on training_plan (date);
create index if not exists idx_training_plan_version on training_plan (version);

-- 7. Audit trail of every plan generation / recalibration.
create table if not exists plan_revisions (
    id            uuid primary key default gen_random_uuid(),
    generated_at  timestamptz not null default now(),
    trigger       text not null,            -- 'initial' | 'recalibration'
    claude_input  jsonb,
    claude_output jsonb,
    tokens_in     integer,
    tokens_out    integer,
    cost_usd      numeric,
    reason        text
);

-- 8. Progress tests scheduled by Claude, results logged by the user.
create table if not exists progress_tests (
    id             uuid primary key default gen_random_uuid(),
    scheduled_date date not null,
    test_type      text not null,
    target_metric  text,
    actual_result  jsonb,
    completed      boolean not null default false,
    notes          text
);
create index if not exists idx_progress_tests_date on progress_tests (scheduled_date);

-- 9. Question/answer log with token accounting.
create table if not exists qa_log (
    id           uuid primary key default gen_random_uuid(),
    asked_at     timestamptz not null default now(),
    question     text not null,
    answer       text,
    context_sent jsonb,
    tokens_in    integer,
    tokens_out   integer,
    cost_usd     numeric
);

-- 10. Operational log surfaced in the in-app Debug tab.
create table if not exists debug_log (
    id        uuid primary key default gen_random_uuid(),
    event_at  timestamptz not null default now(),
    severity  text not null,   -- 'info' | 'warning' | 'error'
    source    text not null,   -- 'garmin' | 'whoop' | 'claude' | 'db' | 'calc'
    message   text not null,
    details   jsonb
);
create index if not exists idx_debug_log_event_at on debug_log (event_at);
create index if not exists idx_debug_log_severity on debug_log (severity);
create index if not exists idx_debug_log_source on debug_log (source);
