import streamlit as st

from core.auth import require_password

require_password()

st.title("Plan")
st.info("The full plan from today to race day, with a Recalibrate button, lands in Phase 1 and 3.")
