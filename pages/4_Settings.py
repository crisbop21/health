import streamlit as st

from core.auth import require_password

require_password()

st.title("Settings")
st.info("Goal editor, device connection status, and manual sync triggers land in Phase 1 to 3.")
