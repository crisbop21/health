"""Entry point for the Personal Health and Training Assistant.

Streamlit auto-discovers the files in pages/ as additional pages. The home
page IS the Today decision screen — the post-run/morning check is the app's
main job, so landing on it beats landing on a list of links."""

import streamlit as st

from core import views, whoop_oauth
from core.auth import require_password

st.set_page_config(page_title="Health & Training Assistant", layout="wide")

# Whoop redirects to the app's base URL (this home page) with ?code=..., so the
# OAuth callback must be handled here as well as on Settings. It runs BEFORE
# anything else: the code is a one-time grant from Whoop.
whoop_oauth.handle_callback()

require_password()

views.render_today()
