"""The password gate was removed. `require_password()` must be a no-op that
renders immediately and never halts the page, no matter the session/config."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from core import auth


def test_require_password_returns_without_blocking():
    assert auth.require_password() is None


def test_require_password_never_calls_streamlit_stop(monkeypatch):
    """Guard against re-introducing a gate: if a fake streamlit is importable,
    require_password() must not touch st.stop()/st.form()."""
    calls = []
    fake_st = SimpleNamespace(
        stop=lambda *a, **k: calls.append("stop"),
        form=lambda *a, **k: calls.append("form"),
        error=lambda *a, **k: calls.append("error"),
        session_state={},
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    auth.require_password()
    assert calls == []
