"""Entry point for the Personal Health and Training Assistant.

Streamlit auto-discovers the files in pages/ as additional pages. This home
screen gates on the app password and links into the sections.
"""

import streamlit as st

from core.auth import require_password

st.set_page_config(page_title="Health & Training Assistant", layout="wide")

require_password()

st.title("Health & Training Assistant")
st.caption("Personal training plan, grounded in your Garmin and Whoop data.")

st.write(
    "Use the sidebar to navigate: **Today**, **Plan**, **Ask**, **Dashboard**, "
    "**Settings**, and **Debug**."
)
