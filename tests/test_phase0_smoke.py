"""Phase 0 smoke tests.

The dependency-light checks (config, logger) always run. Tests that need the UI
or DB stack use importorskip so the suite still passes in a minimal environment;
the live Supabase round-trip additionally requires credentials.
"""

from __future__ import annotations

import uuid

import pytest

from core import logger
from core.config import settings


def test_core_modules_import():
    # config and logger must import with no third-party UI/DB deps installed.
    from core import config

    assert hasattr(config, "settings")


def test_logger_emits_without_db(caplog):
    # With no Supabase creds, log() must still emit a record and not raise.
    with caplog.at_level("INFO", logger="health"):
        logger.info("calc", "phase0 stdout check", {"k": "v"})
    assert any("phase0 stdout check" in r.message for r in caplog.records)


def test_ui_and_db_modules_import():
    pytest.importorskip("streamlit")
    pytest.importorskip("supabase")
    from core import auth, supabase_client  # noqa: F401
    from repositories import debug_log_repo  # noqa: F401


@pytest.mark.skipif(
    not (settings.supabase_url and settings.supabase_key),
    reason="Supabase credentials not configured",
)
def test_debug_log_round_trip():
    pytest.importorskip("supabase")
    from core.supabase_client import get_client
    from repositories import debug_log_repo

    marker = f"phase0-smoke-{uuid.uuid4()}"
    get_client().table("debug_log").insert(
        {"severity": "info", "source": "db", "message": marker}
    ).execute()

    rows = debug_log_repo.recent(limit=50, source="db")
    assert any(r["message"] == marker for r in rows)
