"""Central config. Reads from environment (.env for local dev) first, then
falls back to Streamlit secrets when running inside Streamlit. No other module
should read os.environ or st.secrets directly."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default: str | None = None) -> str | None:
    val = os.environ.get(key)
    if val:
        return val
    # Fall back to Streamlit secrets without requiring Streamlit at import time.
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
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

    def missing(self, keys: list[str]) -> list[str]:
        """Return the subset of required setting names that are unset."""
        return [k for k in keys if not getattr(self, k)]


settings = Settings()
