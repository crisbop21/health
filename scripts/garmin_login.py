"""Mint reusable Garmin OAuth tokens — run this LOCALLY, once.

Garmin returns CAPTCHA_REQUIRED for email/password logins coming from
datacenter IPs (Streamlit Cloud, GitHub Actions), so the cloud app can't log in
with a password. Logging in from your own machine usually works; this script
does that, then saves the resulting OAuth token blob so the app and the daily
sync can resume the session without a password (and without a CAPTCHA).

Usage:
    python -m scripts.garmin_login

It stores the token in Supabase (oauth_tokens, provider=garmin) when SUPABASE_*
is configured, and also prints it so you can paste it into the GARMIN_TOKENS
secret (Streamlit Cloud and GitHub Actions) if you prefer.

Note: if your Garmin account uses MFA, complete the prompt the library shows.
The token is long-lived (~1 year); re-run this when it eventually expires.
"""

from __future__ import annotations

from getpass import getpass

from clients.garmin_client import PROVIDER, _store_token
from core.config import settings


def main() -> int:
    from garminconnect import Garmin

    email = settings.garmin_email or input("Garmin email: ").strip()
    password = settings.garmin_password or getpass("Garmin password: ")

    print("Logging in to Garmin…")
    client = Garmin(email, password)
    client.login()
    token = client.garth.dumps()

    _store_token(token)
    print(f"\nSaved token to Supabase oauth_tokens (provider={PROVIDER}).")
    print("\nOr set this as the GARMIN_TOKENS secret (Streamlit + GitHub Actions):\n")
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
