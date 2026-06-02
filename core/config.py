"""Central config. Streamlit secrets are the source of truth (set in
.streamlit/secrets.toml locally and the Streamlit Cloud secrets manager). An
os.environ fallback is kept so tests and CI can inject values without a secrets
file. No other module should read st.secrets or os.environ directly."""

from __future__ import annotations

import os


def _get(key: str, default: str | None = None) -> str | None:
    # Streamlit secrets first; import lazily so non-UI code stays Streamlit-free.
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    val = os.environ.get(key)
    if val:
        return val
    return default


class Settings:
    @property
    def supabase_url(self) -> str | None:
        return _get("SUPABASE_URL")

    @property
    def supabase_key(self) -> str | None:
        return _get("SUPABASE_KEY")

    @property
    def anthropic_api_key(self) -> str | None:
        return _get("ANTHROPIC_API_KEY")

    @property
    def garmin_email(self) -> str | None:
        return _get("GARMIN_EMAIL")

    @property
    def garmin_password(self) -> str | None:
        return _get("GARMIN_PASSWORD")

    @property
    def whoop_client_id(self) -> str | None:
        return _get("WHOOP_CLIENT_ID")

    @property
    def whoop_client_secret(self) -> str | None:
        return _get("WHOOP_CLIENT_SECRET")

    @property
    def whoop_redirect_uri(self) -> str:
        return _get("WHOOP_REDIRECT_URI", "http://localhost:8501")

    @property
    def app_password(self) -> str | None:
        return _get("APP_PASSWORD")

    @property
    def disable_auth(self) -> bool:
        """Whether the password gate is bypassed. Temporarily defaults to on
        while debugging the Whoop OAuth flow; set DISABLE_AUTH=false (and an
        APP_PASSWORD) to re-enable the gate."""
        return str(_get("DISABLE_AUTH", "true")).strip().lower() in ("1", "true", "yes", "on")

    def missing(self, keys: list[str]) -> list[str]:
        """Return the subset of required setting names that are unset."""
        return [k for k in keys if not getattr(self, k)]


settings = Settings()
