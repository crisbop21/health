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

PAGES = [
    ("pages/1_Today.py", "Today", "📅", "Today's workout, last night's recovery, and this week's tests."),
    ("pages/2_Plan.py", "Plan", "🗓️", "Your training plan and revisions."),
    ("pages/3_Ask.py", "Ask", "💬", "Ask questions grounded in your data."),
    ("pages/6_Dashboard.py", "Dashboard", "📈", "Trends, training volume, and data coverage."),
    ("pages/4_Settings.py", "Settings", "⚙️", "Goal, device sync, and historical backfill."),
    ("pages/5_Debug.py", "Debug", "🔧", "In-app logs for troubleshooting."),
]
left, right = st.columns(2)
for i, (path, label, icon, blurb) in enumerate(PAGES):
    with left if i % 2 == 0 else right:
        st.page_link(path, label=f"**{label}**", icon=icon)
        st.caption(blurb)
