"""Whoop OAuth redirect handling for the Streamlit UI.

Whoop redirects back to a single configured redirect URI with `?code=...`.
That URI is usually the app's base URL, which loads the home page — not
Settings — so the callback must be handled wherever the redirect lands. Both
the home page and Settings call handle_callback() so the token exchange works
either way."""

from __future__ import annotations

import streamlit as st

from clients import whoop_client


def handle_callback() -> None:
    """If the current request carries an OAuth `code`, exchange it for tokens
    and store them. No-op when there's no code. Safe to call on every page."""
    if "code" not in st.query_params:
        return
    code = st.query_params["code"]
    try:
        whoop_client.exchange_code(code)
        st.query_params.clear()
        st.success("Whoop connected. Open **Settings** to sync your data.")
    except Exception as exc:
        st.error(f"Whoop authorization failed: {exc}")
