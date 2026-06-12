from datetime import timedelta

import streamlit as st

from core import clock
from core.auth import require_password
from services import log_service, qa_service, test_service

require_password()

st.title("Today")
today = clock.local_today().isoformat()

# Status line is cached per day in the session and refreshed once on first load.
cache_key = f"today_status_{today}"
if st.button("Refresh status") or cache_key not in st.session_state:
    with st.spinner("Getting today's status…"):
        st.session_state[cache_key] = qa_service.daily_status()

status = st.session_state.get(cache_key, {})

if status.get("ok"):
    st.info(status.get("status") or "")
elif status.get("error"):
    st.warning(f"Status unavailable: {status['error']}")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Today's workout")
    item = status.get("today_item")
    if item:
        st.markdown(f"**{item.get('planned_workout_type', '—')}** · {item.get('intensity_zone', '')}")
        bits = []
        if item.get("planned_distance_km"):
            bits.append(f"{item['planned_distance_km']} km")
        if item.get("planned_duration_minutes"):
            bits.append(f"{item['planned_duration_minutes']} min")
        if item.get("planned_pace"):
            bits.append(item["planned_pace"])
        if bits:
            st.caption(" · ".join(bits))
        if item.get("notes"):
            st.write(item["notes"])
    else:
        st.caption("No planned workout today.")

with col2:
    st.subheader("Last night")
    last = status.get("last_metrics")
    if last:
        c1, c2, c3 = st.columns(3)
        c1.metric("Recovery", last.get("recovery_score") or "—")
        c2.metric("Sleep (h)", last.get("sleep_hours") or "—")
        c3.metric("HRV (ms)", last.get("hrv_ms") or "—")
    else:
        st.caption("No recent metrics. Sync your devices.")

st.subheader("This week's tests")
week_end = (clock.local_today() + timedelta(days=7)).isoformat()
tests = test_service.upcoming_tests(today, week_end).get("rows", [])
if tests:
    for t in tests:
        flag = "done" if t.get("completed") else "scheduled"
        st.write(f"- {t.get('scheduled_date')}: **{t.get('test_type')}** ({flag}) — {t.get('target_metric')}")
else:
    st.caption("No progress tests scheduled this week.")

errors = log_service.recent_logs(limit=3, severity="error").get("rows", [])
if errors:
    with st.expander(f"Recent errors ({len(errors)})", expanded=False):
        for e in errors:
            when = (e.get("event_at") or "")[:19].replace("T", " ")
            st.warning(f"{when} · [{e.get('source')}] {e.get('message')}")
