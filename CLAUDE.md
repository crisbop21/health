# CLAUDE.md

Working agreement for any session touching this repo. Keep it lean; follow it.

## 1. TDD is mandatory

Every behavior change is test-driven:

1. **Write a failing test first** that captures the new behavior or the bug.
2. Write the **minimal** code to make it pass.
3. **Refactor** with the tests green.

Rules:
- No production change lands without a test that would have failed before it.
- Run `pytest -q` before every commit; it must be green.
- Bug fixes start with a test that reproduces the bug.
- Tests mock external systems — **no real network or database in tests**. Live
  Supabase round-trips stay `skip`-guarded behind env vars.

**CI gate:** `.github/workflows/ci.yml` runs `pytest -q` (and byte-compile) on
every push/PR. Keep it green; untested changes go red.

## Commands

```
pytest -q                                              # tests (run before committing)
python -m compileall -q clients core pages repositories services scripts streamlit_app.py
streamlit run streamlit_app.py                         # run the app locally
```

## Architecture boundaries

Dependency direction — never sideways or upward:

```
pages/  →  services/  →  clients/ + repositories/  →  core/
```

- **Pages are dumb.** They call `services/` only — never clients or the DB
  directly.
- **Services are pure Python.** No `streamlit` imports in `services/`, so they
  stay unit-testable.
- **Service contract:** services return `{"ok": bool, ...}` dicts and **never
  raise into the UI**. They log failures and surface them in the return value.
- **One client per external system, one repository per table.** No ad-hoc HTTP
  or DB access outside these.
- **Config only via `core.config.settings`.** No direct `os.environ` /
  `st.secrets` reads elsewhere. A new key means updating `secrets.toml.example`,
  `core/config.py`, and any workflow `env:` block together.
- **Logging only via `core.logger`** (valid sources/severities). Notable actions
  log; it feeds the in-app Debug tab.

## Data model rules

- **Raw vs derived.** `garmin_raw` / `whoop_raw` store payloads verbatim;
  parsing happens only in `services/metrics_service.py`. Derived tables
  (`daily_metrics`, `workouts`) are always rebuildable by replaying raw.
- **Source of truth.** Whoop wins HRV / recovery / sleep; Garmin wins workouts /
  distance / pace. A new metric must declare its source rule.
- **Idempotency.** Ingestion upserts by a natural key (`endpoint, external_id`);
  `recompute_daily_metrics` must stay safe to re-run. Never append-on-sync.
- **Migrations.** Numbered, idempotent, run in the Supabase SQL editor. Any
  schema change ships a migration in `migrations/` and a README note.
