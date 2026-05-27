from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from core.auth import require_password
from repositories import progress_tests_repo, training_plan_repo
from services import plan_service, test_service

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

st.subheader("Progress tests")
if st.button("Schedule progress tests"):
    with st.spinner("Asking Claude to schedule progress tests…"):
        result = test_service.schedule_progress_tests()
    if result.get("ok"):
        st.success(f"Scheduled {result['count']} tests.")
    else:
        st.error(result.get("error", "Scheduling failed. See the Debug tab."))

try:
    tests = progress_tests_repo.get_all()
except Exception as exc:
    tests = []
    st.error(f"Could not load progress tests: {exc}")

if not tests:
    st.caption("No progress tests yet. Click **Schedule progress tests**.")
for t in tests:
    label = f"{t.get('scheduled_date')} · {t.get('test_type')}"
    if t.get("completed"):
        st.write(f"✓ {label} — {t.get('target_metric')}")
        continue
    with st.expander(f"{label} — {t.get('target_metric')}"):
        if t.get("notes"):
            st.caption(t["notes"])
        result_value = st.text_input("Result", key=f"res_{t['id']}", placeholder="e.g. 22:14")
        notes = st.text_input("Notes", key=f"note_{t['id']}")
        if st.button("Mark complete", key=f"done_{t['id']}") and result_value.strip():
            outcome = test_service.log_result(t["id"], result_value.strip(), notes or None)
            if outcome.get("ok"):
                st.success("Logged.")
                st.rerun()
            else:
                st.error(outcome.get("error", "Could not log result."))
