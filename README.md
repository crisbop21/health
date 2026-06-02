# Personal Health and Training Assistant

A single-user web app that ingests biometric data from Garmin and Whoop, uses
Claude to generate and recalibrate a training plan toward a configurable goal,
and answers questions grounded in your data.

See `technical_brief_health_training_assistant.md` and
`implementation_plan_health_training_assistant.md` for the full design.

## Architecture

```
Streamlit UI (pages/)  ->  services/  ->  clients/      (Garmin, Whoop, Claude)
                                      ->  repositories/  (one per table)
                                      ->  core/          (config, logger, supabase)
```

- **UI is dumb**: pages call services only, never clients or the DB directly.
- **Services are pure Python**: no Streamlit imports, easy to test.
- **One client per external system**; **one repository per table**.
- **Logger is global**: everything writes to the `debug_log` table and stdout.

## Setup (local)

1. Python 3.11, then install deps:
   ```
   pip install -r requirements.txt
   ```
2. Copy the secrets template and fill it in:
   ```
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```
   Streamlit secrets are the source of truth, both locally and on Streamlit
   Cloud. (An `os.environ` fallback exists only for tests/CI.)
3. Create a Supabase project (free tier) and run the migrations in
   `migrations/` (`001_initial_schema.sql`, `002_oauth_tokens.sql`,
   `003_rls_policies.sql`, `004_raw_idempotent.sql`) in order in the Supabase
   SQL editor. `001` creates the tables; `003` adds the row-level-security
   policies the API key needs to read and write (without it, syncs fail with
   "new row violates row-level security policy"); `004` adds the external_id
   dedupe key so re-syncing doesn't duplicate raw rows (it clears the raw
   tables, so re-run Backfill afterwards). Alternatively, use the project's
   `service_role` key as `SUPABASE_KEY`, which bypasses RLS.
4. Register a Whoop developer app at developer.whoop.com; set the redirect URI
   to match your local (`http://localhost:8501`) and deployed URLs.
5. Run the app:
   ```
   streamlit run streamlit_app.py
   ```
   The app is gated by `APP_PASSWORD`.

## Tests

```
pytest
```

Import and logger checks run anywhere. The live Supabase round-trip runs only
when `SUPABASE_URL` and `SUPABASE_KEY` are set.

## Deployment

Host on Streamlit Community Cloud. Add every key from
`.streamlit/secrets.toml.example` to the Cloud secrets manager. Never commit
`.streamlit/secrets.toml`.

## Build status

- **Phase 0 (Foundations)** — done: schema migration, `core/` (config, logger,
  supabase client, password gate), Streamlit shell with the five page stubs,
  smoke tests.
- Phases 1–6 — see the implementation plan.
