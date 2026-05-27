import streamlit as st

from core.auth import require_password

require_password()

st.title("Ask")
st.info("A question box grounded in your data, with Q&A history, lands in Phase 4.")
