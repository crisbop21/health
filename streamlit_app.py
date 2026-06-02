"""Entry point for the Personal Health and Training Assistant.

Streamlit auto-discovers the files in pages/ as additional pages. This home
screen gates on the app password and links into the sections.
"""

import streamlit as st

from core.auth import require_password
from core import whoop_oauth

st.set_page_config(page_title="Health & Training Assistant", layout="wide")

# Whoop redirects to the app's base URL (this home page) with ?code=..., so the
# OAuth callback must be handled here as well as on Settings. It runs BEFORE the
# password gate: the code is a one-time grant from Whoop, and letting the gate
# halt the script here is what previously dropped the token on a fresh session.
whoop_oauth.handle_callback()

require_password()

st.title("Health & Training Assistant")
st.caption("Personal training plan, grounded in your Garmin and Whoop data.")

st.write(
    "Use the sidebar to navigate: **Today**, **Plan**, **Ask**, **Dashboard**, "
    "**Settings**, and **Debug**."
)
