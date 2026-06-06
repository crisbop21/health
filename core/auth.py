"""The app no longer has a password gate.

This is a single-user personal app, so the `APP_PASSWORD` login form was
removed. `require_password()` is kept as a no-op so the existing call sites at
the top of `streamlit_app.py` and every page stay valid without churn; it
returns immediately and never blocks rendering.

To re-introduce gating later, restore a real implementation here — the call
sites do not need to change."""

from __future__ import annotations


def require_password() -> None:
    """No-op. The password gate was removed; every page renders immediately."""
    return None
