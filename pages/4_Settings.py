import streamlit as st

from core.auth import require_password
from repositories import goals_repo
from services import sync_service

require_password()

st.title("Settings")

st.subheader("Active goal")
try:
    goal = goals_repo.get_active()
except Exception as exc:
    goal = None
    st.error(f"Could not load the goal: {exc}")

if goal:
    st.json(
        {
            "sport": goal.get("sport"),
            "race_date": goal.get("race_date"),
            "goal_time_seconds": goal.get("goal_time_seconds"),
            "days_per_week": goal.get("days_per_week"),
            "max_session_minutes": goal.get("max_session_minutes"),
        }
    )
else:
    st.info("No active goal. Seed one via migrations/seed_goal.sql. (Editor lands in Phase 3.)")

st.subheader("Devices")
if st.button("Sync Garmin now"):
    with st.spinner("Syncing the last 7 days from Garmin…"):
        result = sync_service.sync_garmin_last_7_days()
    if result.get("ok"):
        st.success(f"Synced. {result['rows_written']} raw rows written.")
    else:
        st.error(f"Garmin sync failed: {result.get('error')}. See the Debug tab.")
