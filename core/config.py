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
    def garmin_tokens(self) -> str | None:
        """Optional pre-minted Garmin OAuth token blob (garth dump). When set,
        the client resumes this session instead of doing a password login,
        which Garmin CAPTCHA-blocks from datacenter IPs. Generate it locally
        with `python -m scripts.garmin_login`."""
        return _get("GARMIN_TOKENS")

    @property
    def garmin_pacing_seconds(self) -> float:
        """Optional delay between per-day Garmin fetches during a sync/backfill.
        0 by default; set to ~1-2s for large backfills to avoid rate limits."""
        try:
            return float(_get("GARMIN_PACING_SECONDS", "0") or 0)
        except ValueError:
            return 0.0

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
    def alert_webhook_url(self) -> str | None:
        """Optional Slack/Discord-compatible incoming webhook. When set, the
        unattended daily sync posts here on real failures."""
        return _get("ALERT_WEBHOOK_URL")

    @property
    def disable_auth(self) -> bool:
        """Whether the password gate is bypassed. Off by default (gate enabled);
        set DISABLE_AUTH=true only for local debugging. The Whoop OAuth callback
        now runs before the gate, so re-connecting works with auth on."""
        return str(_get("DISABLE_AUTH", "false")).strip().lower() in ("1", "true", "yes", "on")

    def missing(self, keys: list[str]) -> list[str]:
        """Return the subset of required setting names that are unset."""
        return [k for k in keys if not getattr(self, k)]


settings = Settings()
