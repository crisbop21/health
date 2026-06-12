"""Page smoke tests: every Streamlit page must render without raising, even
with no database configured (services degrade to error banners, never
exceptions). Skipped when streamlit isn't installed (CI installs it)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

PAGES = [
    "streamlit_app.py",
    "pages/1_Today.py",
    "pages/2_Plan.py",
    "pages/3_Ask.py",
    "pages/4_Settings.py",
    "pages/5_Debug.py",
    "pages/6_Dashboard.py",
]


@pytest.fixture(autouse=True)
def _no_auth_no_db(monkeypatch):
    # Bypass the password gate; leave Supabase unconfigured so any accidental
    # direct DB dependency surfaces as a page exception here.
    monkeypatch.setenv("DISABLE_AUTH", "true")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(page):
    at = AppTest.from_file(str(ROOT / page), default_timeout=15).run()
    assert not at.exception, f"{page} raised: {[e.value for e in at.exception]}"
