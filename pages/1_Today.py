import streamlit as st

from core.auth import require_password

require_password()

st.title("Today")
st.info("Today's workout, last night's recovery, and a status line land here in Phase 4.")
