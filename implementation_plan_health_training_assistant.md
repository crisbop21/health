# Implementation Plan: Personal Health and Training Assistant

**Owner:** Laura Garzon Mora
**Version:** 1.0
**Date:** May 27, 2026
**Build window:** 2 weeks full time (approximately 80 hours)
**Companion to:** technical_brief_health_training_assistant.md

## Recommended approach: end-to-end skeleton first

The smart build order is not "Garmin done, then Whoop, then Claude." That path leaves you with a beautifully integrated Garmin layer on day 5 and nothing usable until day 12. Instead, build a thin vertical slice that touches every layer (one device, one table, one Claude call, one Streamlit page) on day 3. Then deepen each layer in passes.

Why this works for a 2-week solo build:

1. You hit integration risk early (auth flows, API quirks, Supabase connection) when you still have time to pivot
2. You always have a working app to demo to yourself, which keeps motivation up
3. Each pass produces a checkpoint you can roll back to

## Recommended architecture

```
+--------------------------------------------------------------+
|                     Streamlit UI Layer                       |
|  Today | Plan | Ask | Settings | Debug                       |
+--------------------------------------------------------------+
                            |
                            v
+--------------------------------------------------------------+
|                   Service Layer (pure Python)                |
|                                                              |
|  goals_service     plan_service     metrics_service          |
|  qa_service        sync_service     test_service             |
+--------------------------------------------------------------+
        |                |                |              |
        v                v                v              v
+----------------+ +-----------+ +----------------+ +-----------+
| Device clients | | Claude    | | Supabase repo  | | Logger    |
| garmin_client  | | claude_   | | repositories   | | (writes   |
| whoop_client   | | client    | | per table      | | to        |
+----------------+ +-----------+ +----------------+ | debug_log)|
        |                |                |        +-----------+
        v                v                v
+----------------+ +-----------+ +----------------+
| Garmin Connect | | Anthropic | | Supabase       |
| (unofficial)   | | API       | | Postgres       |
| Whoop API v2   | |           | |                |
+----------------+ +-----------+ +----------------+
```

**Principles**

- **UI is dumb.** Streamlit pages call service functions, never device or DB clients directly. This means the UI can be swapped later (FastAPI plus React, mobile app) without rewriting business logic.
- **Services are pure Python.** No Streamlit imports, no global state. Each service function takes inputs and returns outputs. Easy to test.
- **One client per external system.** `garmin_client`, `whoop_client`, `claude_client`. Each handles auth, retries, and rate limits. Nothing else in the codebase talks to those APIs.
- **Repositories own the database.** One file per table. Services call `workouts_repo.insert(...)`, never raw SQL scattered across the codebase.
- **Logger is global.** Every service, client, and repo writes to `debug_log` via a single logger module.

**Folder structure**

```
health_training_assistant/
|
|-- streamlit_app.py              # Entry point, page router
|-- pages/
|   |-- 1_Today.py
|   |-- 2_Plan.py
|   |-- 3_Ask.py
|   |-- 4_Settings.py
|   `-- 5_Debug.py
|
|-- services/
|   |-- goals_service.py
|   |-- plan_service.py
|   |-- metrics_service.py
|   |-- qa_service.py
|   |-- sync_service.py
|   `-- test_service.py
|
|-- clients/
|   |-- garmin_client.py
|   |-- whoop_client.py
|   `-- claude_client.py
|
|-- repositories/
|   |-- goals_repo.py
|   |-- garmin_raw_repo.py
|   |-- whoop_raw_repo.py
|   |-- daily_metrics_repo.py
|   |-- workouts_repo.py
|   |-- training_plan_repo.py
|   |-- plan_revisions_repo.py
|   |-- progress_tests_repo.py
|   |-- qa_log_repo.py
|   `-- debug_log_repo.py
|
|-- core/
|   |-- logger.py
|   |-- config.py                 # loads .env / Streamlit secrets
|   |-- supabase_client.py        # singleton Supabase connection
|   `-- pace_zones.py             # deterministic calculations
|
|-- tests/
|   |-- test_garmin_client.py
|   |-- test_whoop_client.py
|   |-- test_plan_service.py
|   `-- test_repositories.py
|
|-- migrations/
|   |-- 001_initial_schema.sql
|   `-- 002_add_progress_tests.sql
|
|-- .env.example
|-- requirements.txt
|-- README.md
`-- .streamlit/
    `-- secrets.toml              # not committed
```

## Phase overview

| Phase | Days | Goal | Tests at end |
|---|---|---|---|
| 0 | 1 | Foundations: repo, env, Supabase, secrets | Connection tests |
| 1 | 2 to 3 | End-to-end skeleton: one device, one Claude call, one plan view | Smoke test the full flow |
| 2 | 4 to 5 | Both devices ingesting reliably into raw tables | Sync tests, replay tests |
| 3 | 6 to 8 | Plan generation and recalibration with full goal config | Plan tests, recalibration tests |
| 4 | 9 to 10 | Q&A, progress tests, Today page | Q&A correctness, test scheduling |
| 5 | 11 to 12 | Debug tab, logging completeness, error paths | Failure injection tests |
| 6 | 13 to 14 | Deployment, polish, one full week of self-use | Live use acceptance |

---

## Phase 0: Foundations (Day 1, 6 to 8 hours)

**Goal:** A repo on GitHub, a Supabase project, a deployed empty Streamlit app, and all secrets working locally and in the cloud.

### Steps

1. **Create GitHub repo** `health-training-assistant`, private, with Python `.gitignore`
2. **Set up local environment**
   - Python 3.11 virtualenv
   - `requirements.txt` with: `streamlit`, `supabase`, `anthropic`, `python-garminconnect`, `requests`, `python-dotenv`, `pandas`, `pytest`
3. **Create Supabase project** (free tier)
   - Get the project URL and the service role key
   - Get the anon key for client-side reads if needed
4. **Write initial schema migration** `migrations/001_initial_schema.sql` with all 10 tables from the brief
5. **Run the migration** in the Supabase SQL editor
6. **Set up secrets**
   - Local: `.env` with `SUPABASE_URL`, `SUPABASE_KEY`, `ANTHROPIC_API_KEY`, `GARMIN_EMAIL`, `GARMIN_PASSWORD`, `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, `APP_PASSWORD`
   - `.env.example` committed with empty values
7. **Build `core/config.py`** to load secrets from env or `st.secrets`
8. **Build `core/supabase_client.py`** as a singleton
9. **Build `core/logger.py`** that writes to both stdout and `debug_log` table
10. **Build `streamlit_app.py`** with a password gate and empty page stubs
11. **Deploy to Streamlit Community Cloud**, add secrets in the dashboard
12. **Register the Whoop developer app** at developer.whoop.com, save `client_id` and `client_secret`

### Dependencies

None, this is the start.

### Phase 0 tests

- Run `streamlit run streamlit_app.py` locally, app loads and password gate works
- Open the deployed Streamlit URL, app loads with secrets
- Run a script that inserts and reads one row from `debug_log` via `supabase_client`
- Verify all 10 tables exist in Supabase SQL editor with the correct columns

**Checkpoint:** Empty app deployed, database schema in place, secrets working in two environments.

---

## Phase 1: End-to-end skeleton (Days 2 to 3, 12 to 16 hours)

**Goal:** A vertical slice that ingests one day of Garmin data, sends it to Claude, generates a placeholder 7-day plan, and shows it in the Plan page. This is the riskiest phase because it touches every external system.

### Steps

1. **Build `clients/garmin_client.py`**
   - `login()` using `python-garminconnect`
   - `fetch_recent_activities(days=7)`
   - `fetch_daily_metrics(date)`
   - Store the raw JSON response, do not parse yet
2. **Build `repositories/garmin_raw_repo.py`** with `insert(payload, endpoint, recorded_at)`
3. **Build `services/sync_service.py`** with `sync_garmin_last_7_days()`
   - Calls garmin_client, writes to garmin_raw_repo, logs each step
4. **Build `clients/claude_client.py`**
   - `generate_plan(goal_dict, recent_metrics_dict) -> dict`
   - Uses structured output (JSON mode) returning a list of daily plan items
   - System prompt loaded from a `prompts/plan_generation.md` file
5. **Build `services/plan_service.py`** with `generate_initial_plan(goal_id)`
   - Reads the goal, fetches recent metrics summary, calls claude_client, writes to training_plan and plan_revisions
6. **Build `repositories/goals_repo.py`, `training_plan_repo.py`, `plan_revisions_repo.py`**
7. **Seed one goal manually** via SQL: a December marathon with placeholder values
8. **Build `pages/2_Plan.py`** to display the training_plan table as a dataframe
9. **Add a "Generate plan" button** that calls `plan_service.generate_initial_plan()`
10. **Add a "Sync Garmin now" button** in Settings that calls `sync_service.sync_garmin_last_7_days()`

### Dependencies

- Phase 0 complete
- Garmin login working (this can take an hour of debugging, MFA can complicate things)
- Anthropic API key has credit

### Phase 1 tests

- Click "Sync Garmin now", check that `garmin_raw` has new rows
- Click "Generate plan", check that `training_plan` has 1 plan per day for the goal window, and `plan_revisions` has 1 row with claude_input and claude_output
- Reload the Plan page, see the generated plan in a table
- Check `debug_log` for one info line per step, no errors
- Manually break the Garmin password in `.env`, click sync, confirm the error appears in `debug_log` with severity error

**Checkpoint:** A working app that can pull your real data, generate a real plan, and display it. The rest of the build is deepening this.

---

## Phase 2: Both devices ingesting reliably (Days 4 to 5, 12 to 16 hours)

**Goal:** Whoop integrated end-to-end, both devices syncing on demand, derived `daily_metrics` table populated by source-resolution logic.

### Steps

1. **Build `clients/whoop_client.py`**
   - OAuth 2.0 authorization code flow (one-time setup, save refresh token)
   - `fetch_recoveries(start, end)`, `fetch_sleeps(start, end)`, `fetch_workouts(start, end)`, `fetch_cycles(start, end)`
   - Token refresh logic
2. **Build `repositories/whoop_raw_repo.py`**
3. **Add Whoop OAuth callback handling**
   - One-time flow: a Streamlit page that shows a "Connect Whoop" button, redirects to Whoop auth, captures the code, exchanges for tokens, stores refresh token in Supabase
4. **Extend `sync_service.py`** with `sync_whoop_last_7_days()` and `sync_all_devices()`
5. **Build `services/metrics_service.py`**
   - `recompute_daily_metrics(date_range)` that reads from both raw tables and writes resolved values to `daily_metrics`
   - Whoop wins for HRV, recovery, sleep
   - Garmin wins for workouts, pace, distance
6. **Build `repositories/daily_metrics_repo.py` and `workouts_repo.py`**
7. **Add "Sync all" and "Recompute metrics" buttons** in Settings
8. **Add device connection status** to Settings (last successful sync per device)

### Dependencies

- Phase 1 complete
- Whoop developer app registered with redirect URI matching your Streamlit URL

### Phase 2 tests

- Connect Whoop end-to-end via the OAuth flow, confirm refresh token stored
- Sync both devices, confirm `garmin_raw` and `whoop_raw` both have new rows
- Run "Recompute metrics", confirm `daily_metrics` has one row per day with source_hrv = whoop and source_sleep = whoop
- Delete a row from `daily_metrics`, click "Recompute metrics" again, confirm it is restored from raw data
- Disconnect internet, sync, confirm graceful error in `debug_log` not a crash

**Checkpoint:** Both devices feeding the database reliably, with raw preservation and source resolution working.

---

## Phase 3: Plan generation and recalibration with full goal config (Days 6 to 8, 18 to 22 hours)

**Goal:** A real, configurable goal in the UI, full plan from today to race day, on-demand recalibration that respects recent metrics.

### Steps

1. **Build `pages/4_Settings.py`** with a complete goal editor
   - Sport, race date, goal time, days per week, max session minutes, time windows, blackout dates
   - Save button writes to `goals` table (always a new row with active=true, previous goals set to active=false)
2. **Improve `claude_client.generate_plan()`**
   - Pass full goal context including blackout dates and time windows
   - Pass last 14 days of daily_metrics summary
   - Return structured plan with: date, workout type, distance, duration, pace zone, notes
   - Use Claude Sonnet 4.5 with extended thinking if needed for plan coherence
3. **Build `core/pace_zones.py`**
   - Deterministic calculations for easy, marathon, threshold, interval paces from goal time
   - Used as guardrails on Claude's output (warn if pace deviates from zone)
4. **Add plan generation guardrails**
   - 10 percent weekly mileage cap check
   - Tapering check in last 3 weeks
   - Long run on a non-blackout day
   - If violated, log warning and proceed (do not block)
5. **Build `services/plan_service.recalibrate_plan(reason)`**
   - Fetches current plan from today onward
   - Fetches last 7 to 14 days of metrics
   - Calls Claude with the current plan plus recent data
   - Writes new plan rows with incremented version
   - Logs to `plan_revisions` with reason
6. **Add "Recalibrate" button to Plan page**
7. **Improve Plan page UI**
   - Full table from today to race date
   - Current day highlighted
   - Filter by week
   - Show plan version

### Dependencies

- Phase 2 complete (real metrics available)
- Claude API working reliably

### Phase 3 tests

- Edit the goal, change race date, confirm new goal row with active=true
- Generate plan, confirm it spans from today to race date with no plans on blackout dates
- Confirm long runs land on available days only
- Confirm weekly mileage progression follows the 10 percent rule, log warnings if Claude violates
- Click recalibrate, confirm new plan rows with version 2, old version 1 rows preserved
- Confirm `plan_revisions` has 2 rows with inputs and outputs
- Manually corrupt the goal (race date in the past), click generate, confirm graceful error not a crash

**Checkpoint:** Full marathon plan that respects every constraint, recalibrates on demand, with version history.

---

## Phase 4: Q&A, progress tests, Today page (Days 9 to 10, 12 to 14 hours)

**Goal:** The Today page is useful in the morning, Q&A grounded in real data, progress tests scheduled and loggable.

### Steps

1. **Build `services/qa_service.py`**
   - `ask(question)` builds a context bundle: current goal, last 7 days of metrics, this week's plan
   - Calls Claude with context plus question
   - Writes to `qa_log` with question, answer, context_sent, tokens
2. **Build `pages/3_Ask.py`**
   - Question input, answer display
   - History of past Q&A, most recent first
3. **Build `services/test_service.py`**
   - `schedule_progress_tests(plan_id)`: Claude picks 3 to 5 progress tests across the plan, writes to `progress_tests`
   - Test types: 5K time trial, 10K time trial, long run benchmark, HRV trend check
4. **Build `pages/1_Today.py`**
   - Today's workout from `training_plan`
   - Last night's recovery and sleep from `daily_metrics`
   - One-line status from Claude (cached, refreshed once per day) on recovery quality
   - Upcoming progress test if scheduled this week
5. **Add progress test logging UI** in the Plan page
   - Click a scheduled test, enter result, mark complete

### Dependencies

- Phase 3 complete

### Phase 4 tests

- Ask "How is my training going?", confirm answer references real data from `daily_metrics`
- Ask a question that has no data ("what did I eat yesterday"), confirm graceful "I don't have that data" answer
- Confirm `qa_log` has every Q&A with tokens recorded
- Generate plan and schedule progress tests, confirm 3 to 5 rows in `progress_tests` spaced across the plan
- Log a completed test result, confirm `progress_tests.completed = true` and `actual_result` populated
- Reload Today page each morning for 3 days, confirm it shows the right day and the status is fresh

**Checkpoint:** The app is now genuinely useful daily, not just a plan viewer.

---

## Phase 5: Debug tab, logging completeness, error paths (Days 11 to 12, 10 to 12 hours)

**Goal:** Every error visible in the app, no need to open Supabase. Failure modes are graceful.

### Steps

1. **Build `pages/5_Debug.py`**
   - Table view of `debug_log` rows, most recent first
   - Filters: severity (info, warning, error), source (garmin, whoop, claude, db, calc), date range
   - Expand any row to see the full details jsonb
2. **Audit every service and client for logging gaps**
   - Every external API call should log: endpoint, duration, status, tokens or rows returned
   - Every database write should log: table, operation, row count
   - Every calculation should log: inputs and outputs
3. **Add explicit error handling**
   - Garmin login failure: log error, show banner in app, do not crash
   - Whoop token expired: auto-refresh, log info, retry once
   - Claude API timeout: log error, return previous plan version, show banner
   - Supabase unavailable: log error, show banner, disable write actions
4. **Add a "Recent errors" widget to the Today page** showing the latest 3 errors if any
5. **Failure injection testing**
   - Temporarily break each external system one at a time and confirm graceful handling

### Dependencies

- Phase 4 complete

### Phase 5 tests

- Open Debug tab, confirm filters work and rows are sortable
- Break Garmin password, sync, confirm error visible in Debug tab and banner on Settings page, app does not crash
- Set ANTHROPIC_API_KEY to invalid, click recalibrate, confirm error visible and previous plan unchanged
- Disconnect from internet, click sync, confirm timeout error logged not a crash
- Confirm no error in production has only `print()` output, every error reaches `debug_log`

**Checkpoint:** Operational quality, you can debug anything from inside the app.

---

## Phase 6: Deployment, polish, real-world acceptance (Days 13 to 14, 8 to 10 hours)

**Goal:** Deployed cleanly, used for one full week without manual database intervention.

### Steps

1. **Final deployment polish**
   - All secrets in Streamlit Cloud, none in code
   - README with setup instructions for future-Laura
   - Pin all package versions in `requirements.txt`
2. **Mobile readability pass**
   - Open every page on your phone, confirm tables are scrollable, buttons tappable
   - Reduce column count on Plan page for narrow viewports
3. **Cosmetic polish**
   - Single accent color throughout
   - Consistent spacing and typography
   - Remove any Streamlit default elements you don't want
4. **Set up one week of real use**
   - Each morning: open Today page, see plan and recovery
   - End of day: sync devices, log progress test if any
   - End of week: recalibrate based on metrics
5. **Final retrospective document**
   - What broke, what worked, what to defer to v2

### Dependencies

- Phase 5 complete

### Phase 6 tests (acceptance)

- For 7 consecutive days, open the app each morning, use it as intended, with zero manual SQL or code intervention
- Recalibrate once mid-week, confirm new plan reflects recent metrics
- Complete one progress test, log the result
- At end of week, all DoD criteria from the brief pass

**Checkpoint:** v1 complete, ready to use for the full marathon cycle.

---

## Critical path and risk

**Critical path:** Phase 0 to 1 must complete in 3 days. If Phase 1 slips past day 4, scope cuts are needed.

**Highest risks**

1. **Garmin auth via `python-garminconnect`** can have MFA issues. Mitigation: keep a manual FIT file fallback in mind for Phase 2.
2. **Whoop OAuth callback URL** must match exactly between developer dashboard and deployed Streamlit URL. Mitigation: register both `localhost` and the Streamlit Cloud URL in dev dashboard.
3. **Claude plan output inconsistency.** Mitigation: tight JSON schema in the prompt, validation in `plan_service`, log all revisions for prompt tuning.
4. **Scope creep on UI polish.** Mitigation: timebox Phase 6, every cosmetic change must wait until phase 5 complete.

## Scope cut order if behind schedule

If by end of day 7 you are behind, cut in this order:

1. Cut progress test scheduling, log manually instead
2. Cut Today page Claude status line, show plan only
3. Cut Q&A for v1, defer to v1.1
4. Cut Whoop, run on Garmin only with Whoop as v1.1

Do not cut: schema, logging, debug tab, plan generation, recalibration.
