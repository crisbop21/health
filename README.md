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
3. Create a Supabase project (free tier) and run the schema migration
   `migrations/001_initial_schema.sql` in the Supabase SQL editor. This creates
   all 10 tables.
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
