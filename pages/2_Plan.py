from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from core.auth import require_password
from repositories import training_plan_repo
from services import plan_service

require_password()

st.title("Plan")

c1, c2 = st.columns(2)
with c1:
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
with c2:
    reason = st.text_input("Recalibration reason", placeholder="e.g. low recovery this week")
    if st.button("Recalibrate"):
        with st.spinner("Recalibrating the remaining plan…"):
            result = plan_service.recalibrate_plan(reason or "manual recalibration")
        if result.get("ok"):
            st.success(f"Recalibrated to v{result['version']} — {result['count']} days.")
            if result.get("summary"):
                st.caption(result["summary"])
        else:
            st.error(result.get("error", "Recalibration failed. See the Debug tab."))

try:
    rows = training_plan_repo.get_plan()
except Exception as exc:
    st.error(f"Could not load the plan: {exc}")
    rows = []

if not rows:
    st.info("No plan yet. Click **Generate plan** to create one from your active goal.")
    st.stop()

today = date.today().isoformat()
version = rows[0].get("version")
df = pd.DataFrame(rows)


def _week_start(d: str) -> str:
    dt = datetime.fromisoformat(d).date()
    return (dt - timedelta(days=dt.weekday())).isoformat()


df["_week"] = df["date"].map(_week_start)
weeks = sorted(df["_week"].unique())
choice = st.selectbox(
    "Week",
    ["All weeks"] + [f"Week of {w}" for w in weeks],
)
view = df if choice == "All weeks" else df[df["_week"] == choice.replace("Week of ", "")]

st.caption(f"Plan version {version} — {len(view)} of {len(df)} days. Today is highlighted.")

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
    if c in view.columns
]
view = view[display_cols]


def _highlight_today(row):
    color = "background-color: #1f4e5f" if row["date"] == today else ""
    return [color] * len(row)


st.dataframe(
    view.style.apply(_highlight_today, axis=1),
    use_container_width=True,
    hide_index=True,
)
