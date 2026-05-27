import pandas as pd
import streamlit as st

from core.auth import require_password
from repositories import debug_log_repo

require_password()

st.title("Debug")
st.caption("Operational log. Filters and full row inspection are deepened in Phase 5.")

col1, col2 = st.columns(2)
severity = col1.selectbox("Severity", ["all", "info", "warning", "error"])
source = col2.selectbox("Source", ["all", "garmin", "whoop", "claude", "db", "calc"])

try:
    rows = debug_log_repo.recent(
        severity=None if severity == "all" else severity,
        source=None if source == "all" else source,
    )
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("No log rows yet.")
except Exception as exc:
    st.error(f"Could not load debug_log: {exc}")
