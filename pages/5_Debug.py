from datetime import date, datetime, time, timedelta, timezone

import streamlit as st

from core.auth import require_password
from repositories import debug_log_repo

require_password()

st.title("Debug")
st.caption("Operational log. Click a row to inspect full details.")

c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
severity = c1.selectbox("Severity", ["all", "info", "warning", "error"])
source = c2.selectbox("Source", ["all", "garmin", "whoop", "claude", "db", "calc"])
since_date = c3.date_input("Since", value=date.today() - timedelta(days=7))
limit = c4.number_input("Limit", min_value=10, max_value=2000, value=200, step=50)

since_iso = datetime.combine(since_date, time.min, tzinfo=timezone.utc).isoformat()

try:
    rows = debug_log_repo.recent(
        limit=int(limit),
        severity=None if severity == "all" else severity,
        source=None if source == "all" else source,
        since=since_iso,
    )
except Exception as exc:
    st.error(f"Could not load debug_log: {exc}")
    rows = []

if not rows:
    st.info("No log rows in this window.")

ICONS = {"info": "·", "warning": "!", "error": "✗"}

for row in rows:
    icon = ICONS.get(row.get("severity"), "·")
    when = (row.get("event_at") or "")[:19].replace("T", " ")
    header = f"{icon} {when} · [{row.get('source')}] {row.get('message')}"
    with st.expander(header):
        st.json(
            {
                "severity": row.get("severity"),
                "source": row.get("source"),
                "event_at": row.get("event_at"),
                "message": row.get("message"),
                "details": row.get("details"),
            }
        )
