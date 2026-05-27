# Technical Brief: Personal Health and Training Assistant

**Owner:** Laura Garzon Mora
**Version:** 2.0 (final draft)
**Date:** May 27, 2026

## 1. Context and goal

Build a personal web app for my own use that ingests biometric data from Garmin and Whoop, uses Claude to generate and adjust a training plan toward a configurable goal (starting with a December marathon), and lets me ask questions about my data. The app must be sport-agnostic and goal-configurable so I can change the target later without rebuilding.

## 2. MVP scope

**In scope for v1**

- Pull daily metrics from Garmin (workouts, HR, HRV, sleep, steps) and Whoop (recovery, strain, HRV, sleep)
- Configurable goal: sport, race date, target finish time, available days per week, max session length, time windows in the day, blackout dates
- Initial training plan generation by Claude, full plan from today to race day visible end to end
- On-demand recalibration via a button, no scheduled job
- Progress tests (time trials, HRV trend checks, long run benchmarks), Claude picks which one based on training phase
- Question box where I can ask Claude about my data
- Daily plan table view, current day highlighted
- In-app debug tab showing calculation errors and database issues

**Deferred to v2**

- Nutrition logging (manual plus photo-based)
- Photo-based food recognition via Claude
- Scheduled automatic recalibration
- Partner or second-user access
- Mobile-native UI

## 3. Goal parameters (configurable in app, not hardcoded)

All of these are stored in a `goals` table and editable from the UI:

- Sport (default: running)
- Race or target event date (default: December 2026)
- Goal finish time
- Current weekly volume (fetched from devices, not user-entered)
- Available training days per week
- Max session length per weekday
- Preferred time windows per day
- Blackout dates (single days or ranges)

## 4. Data sources

| Source | Method | Status |
|---|---|---|
| Garmin Connect | `python-garminconnect` (unofficial Python library) | Need to authenticate with Garmin credentials |
| Whoop | Official Whoop Developer API v2 (OAuth 2.0) | Need to register app at developer.whoop.com, free with Whoop membership |

**Source of truth rules**

- For HRV, recovery, and sleep: Whoop wins
- For workouts, distance, pace, GPS: Garmin wins
- Both sources stored raw in separate tables, conflicts resolved at the derived layer

**Reliability note**

The unofficial Garmin library can break when Garmin changes their site. Fallback: manual FIT file import or temporary Whoop-only mode.

## 5. AI layer

Claude (via Anthropic API) handles:

- Initial plan generation from goal parameters and recent device data
- On-demand recalibration (user clicks a button, Claude regenerates the remaining plan based on the last 7 to 14 days of metrics)
- Free-text Q&A in the question box, grounded in stored data
- Choosing which progress test to recommend based on training phase

Deterministic Python code handles:

- All device API calls and data ingestion
- Database reads and writes
- Pace zone calculations and basic guardrails (10 percent weekly mileage cap)
- Logging

Cost ceiling: none for v1, optimize later if needed.

## 6. Technical stack

- Python 3.11
- Supabase (Postgres) for storage
- Streamlit for UI, hosted on Streamlit Community Cloud (free tier)
- Secrets in Streamlit Cloud secrets manager and `.env` for local development
- Single-user app, simple password protection in Streamlit (no Supabase Auth needed for v1)
- Anthropic Python SDK for Claude calls
- `python-garminconnect` for Garmin
- `requests` plus OAuth flow for Whoop

## 7. Database schema (draft)

**Tables**

`goals`

- id, sport, race_date, goal_time_seconds, days_per_week, max_session_minutes, time_windows jsonb, blackout_dates jsonb, created_at, updated_at, active boolean

`garmin_raw`

- id, recorded_at, endpoint, payload jsonb, ingested_at

`whoop_raw`

- id, recorded_at, endpoint, payload jsonb, ingested_at

`daily_metrics` (derived, source-resolved)

- id, date, hrv_ms, resting_hr, sleep_hours, recovery_score, strain, source_hrv, source_sleep, computed_at

`workouts` (derived from Garmin, manual fallback possible)

- id, date, sport, distance_km, duration_seconds, avg_pace, avg_hr, max_hr, source, raw_id

`training_plan`

- id, date, planned_sport, planned_workout_type, planned_distance_km, planned_duration_minutes, planned_pace, intensity_zone, notes, version, generated_at

`plan_revisions`

- id, generated_at, trigger (initial or recalibration), claude_input jsonb, claude_output jsonb, tokens_in, tokens_out, cost_usd, reason

`progress_tests`

- id, scheduled_date, test_type, target_metric, actual_result jsonb, completed boolean, notes

`qa_log`

- id, asked_at, question, answer, context_sent jsonb, tokens_in, tokens_out, cost_usd

`debug_log`

- id, event_at, severity (info, warning, error), source (garmin, whoop, claude, db, calc), message, details jsonb

**Rule:** raw payloads from each device are kept indefinitely in the `_raw` tables. Derived tables can be recomputed at any time by replaying the raw data.

## 8. UI structure (Streamlit, mobile-readable)

Four pages, designed minimal and dashboard-style:

**1. Today**

- Today's planned workout
- Last night's recovery and sleep
- One-line status from Claude (e.g. "Recovery is low, consider easy pace today")

**2. Plan**

- Full table from today to race day
- Current day highlighted
- Recalibrate button (on-demand)
- Filter by week

**3. Ask**

- Question box
- History of past Q&A

**4. Debug**

- In-app log viewer
- Filter by severity, source, date
- Visible only to me

**5. Settings**

- Goal parameters (sport, race date, goal time, availability, blackouts)
- Device connection status (Garmin, Whoop)
- Manual sync trigger

**Design principles:** minimal, high information density, single accent color, no decorative imagery, readable on mobile but not gesture-optimized.

## 9. Logging and observability

Every operation writes to `debug_log`:

- All Claude API calls (input summary, output summary, latency, tokens, cost, status)
- All Supabase writes (table, row id, operation, status)
- All device API calls (endpoint, status code, retry count, error if any)
- Every plan calculation (inputs, intermediate values, final output)
- Every recalibration (what changed and why)

The Debug tab in the UI surfaces these with filters. Errors are also written to stdout so they show up in Streamlit Cloud logs.

## 10. Definition of Done

The app is done when all of the following are true:

1. Garmin and Whoop are connected, data flows daily into the raw tables
2. Goal parameters are editable in the Settings page and persist across sessions
3. Claude generates a full training plan from today to race day, visible in the Plan view
4. The Recalibrate button triggers Claude to regenerate the remaining plan based on recent metrics, and the change is logged in `plan_revisions`
5. The Ask page returns useful answers grounded in my data
6. Progress tests are scheduled by Claude based on training phase, and I can log results in the UI
7. The Debug tab shows all calculation errors and database issues, filterable by source and severity, with no need to open Supabase directly
8. I have used the app for one full week without manual database intervention

## 11. Out of scope (explicit)

- Nutrition logging
- Photo-based food recognition
- Partner or multi-user access
- Native mobile app
- Scheduled automatic recalibration
- Google Calendar integration
- Public sharing of plans
- Wearable device alternatives beyond Garmin and Whoop

## 12. Open risks

- `python-garminconnect` may break with Garmin site changes. Mitigation: monitor library, fall back to manual FIT import or Whoop-only mode.
- Whoop API rate limits may affect frequent recalibration. Mitigation: cache derived data, on-demand recalibration limits user-triggered calls.
- Claude plan generation may be inconsistent across runs. Mitigation: store every plan revision with inputs and outputs so we can audit and prompt-tune.
