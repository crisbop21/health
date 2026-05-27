import pandas as pd
import streamlit as st

from core.auth import require_password
from repositories import training_plan_repo
from services import plan_service

require_password()

st.title("Plan")

if st.button("Generate plan", type="primary"):
    with st.spinner("Asking Claude to build your plan…"):
        result = plan_service.generate_initial_plan()
    if result.get("ok"):
        st.success(
            f"Generated plan v{result['version']} — {result['count']} days "
            f"(~${result.get('cost_usd') or 0:.2f})."
        )
        if result.get("summary"):
            st.caption(result["summary"])
    else:
        st.error(result.get("error", "Plan generation failed. See the Debug tab."))

try:
    rows = training_plan_repo.get_plan()
except Exception as exc:
    st.error(f"Could not load the plan: {exc}")
    rows = []

if rows:
    version = rows[0].get("version")
    st.caption(f"Showing plan version {version} — {len(rows)} days.")
    df = pd.DataFrame(rows)
    display_cols = [
        c
        for c in [
            "date",
            "planned_sport",
            "planned_workout_type",
            "planned_distance_km",
            "planned_duration_minutes",
            "planned_pace",
            "intensity_zone",
            "notes",
        ]
        if c in df.columns
    ]
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
else:
    st.info("No plan yet. Click **Generate plan** to create one from your active goal.")
