from datetime import datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from core import clock, ui
from core.auth import require_password
from services import plan_service, test_service

st.set_page_config(page_title="Plan · Health & Training", layout="wide")
require_password()

st.title("Plan")
ui.race_header()

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

plan = plan_service.current_plan()
rows = plan.get("rows", [])
if not plan.get("ok"):
    st.error(f"Could not load the plan: {plan.get('error')}")

if not rows:
    st.info("No plan yet. Click **Generate plan** to create one from your active goal.")
    st.stop()

today = clock.local_today().isoformat()
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

# Close the loop: mark plan days that have a matching synced workout.
adherence = plan_service.adherence(weeks=8)
completed = set(adherence.get("completed_dates") or []) if adherence.get("ok") else set()
view = view.copy()
view["done"] = view["date"].map(lambda d: "✓" if d in completed else "")

display_cols = [
    c
    for c in [
        "date",
        "done",
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
    width="stretch",
    hide_index=True,
)

st.subheader("Adherence")
if adherence.get("ok") and adherence.get("weeks"):
    adf = pd.DataFrame(adherence["weeks"])
    melted = adf.melt(
        id_vars="week", value_vars=["planned_km", "actual_km"],
        var_name="kind", value_name="km",
    )
    melted["kind"] = melted["kind"].map({"planned_km": "planned", "actual_km": "done"})
    chart = (
        alt.Chart(melted)
        .mark_bar()
        .encode(
            x=alt.X("week:N", title=None, axis=alt.Axis(labelAngle=0)),
            xOffset="kind:N",
            y=alt.Y("km:Q", title="km / week"),
            color=alt.Color(
                "kind:N",
                scale=alt.Scale(domain=["planned", "done"], range=["#b0bec5", "#00897b"]),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=["week:N", "kind:N", alt.Tooltip("km:Q", format=".1f")],
        )
        .properties(height=220)
    )
    st.altair_chart(chart, use_container_width=True)
    pct = adherence.get("adherence_pct")
    st.caption(
        f"Last 8 weeks: **{adherence['actual_km']} of {adherence['planned_km']} planned km"
        + (f" ({pct}%)**." if pct is not None else "**.")
        + " Future plan days don't count against you."
    )
else:
    st.caption("Adherence appears once the plan overlaps your synced workouts.")

st.subheader("Progress tests")
if st.button("Schedule progress tests"):
    with st.spinner("Asking Claude to schedule progress tests…"):
        result = test_service.schedule_progress_tests()
    if result.get("ok"):
        st.success(f"Scheduled {result['count']} tests.")
    else:
        st.error(result.get("error", "Scheduling failed. See the Debug tab."))

tests_result = test_service.all_tests()
tests = tests_result.get("rows", [])
if not tests_result.get("ok"):
    st.error(f"Could not load progress tests: {tests_result.get('error')}")

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
