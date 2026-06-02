"""Simple single-user password gate. Every page calls require_password() at the
top; it halts rendering until the correct APP_PASSWORD is entered.

The gate can be turned off by setting DISABLE_AUTH=true in secrets/env — useful
while debugging the Whoop OAuth redirect, which can otherwise be interrupted by
the password form on a fresh session. Re-enable by removing that flag."""

from __future__ import annotations

import hmac

import streamlit as st

from core.config import settings


def require_password() -> None:
    if settings.disable_auth:
        st.caption("⚠️ Password gate disabled (DISABLE_AUTH). Anyone with the URL can access this app.")
        return

    if st.session_state.get("authenticated"):
        return

    expected = settings.app_password
    if not expected:
        st.error("APP_PASSWORD is not configured. Set it in secrets to use the app.")
        st.stop()

    with st.form("login"):
        entered = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter")

    if submitted:
        if hmac.compare_digest(entered, expected):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    if not st.session_state.get("authenticated"):
        st.stop()
