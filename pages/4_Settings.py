import secrets

import streamlit as st

from clients import whoop_client
from core.auth import require_password
from repositories import garmin_raw_repo, goals_repo, whoop_raw_repo
from services import metrics_service, sync_service

require_password()

st.title("Settings")

# --- Whoop OAuth callback: handle ?code=... when Whoop redirects back here ---
if "code" in st.query_params:
    code = st.query_params["code"]
    try:
        whoop_client.exchange_code(code)
        st.query_params.clear()
        st.success("Whoop connected.")
    except Exception as exc:
        st.error(f"Whoop authorization failed: {exc}")

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


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


col_g, col_w = st.columns(2)
with col_g:
    st.markdown("**Garmin**")
    last = _safe(garmin_raw_repo.latest_ingested_at)
    st.caption(f"Last sync: {last or 'never'}")
with col_w:
    st.markdown("**Whoop**")
    connected = _safe(whoop_client.is_connected, False)
    last_w = _safe(whoop_raw_repo.latest_ingested_at)
    st.caption(f"{'Connected' if connected else 'Not connected'} · last sync: {last_w or 'never'}")
    if not connected:
        state = st.session_state.setdefault("whoop_oauth_state", secrets.token_urlsafe(16))
        st.link_button("Connect Whoop", whoop_client.authorize_url(state))

c1, c2 = st.columns(2)
with c1:
    if st.button("Sync all devices"):
        with st.spinner("Syncing Garmin and Whoop…"):
            result = sync_service.sync_all_devices()
        g, w = result["garmin"], result["whoop"]
        (st.success if g.get("ok") else st.error)(
            f"Garmin: {g.get('rows_written', 0)} rows" if g.get("ok") else f"Garmin: {g.get('error')}"
        )
        (st.success if w.get("ok") else st.error)(
            f"Whoop: {w.get('rows_written', 0)} rows" if w.get("ok") else f"Whoop: {w.get('error')}"
        )
with c2:
    if st.button("Recompute metrics"):
        with st.spinner("Rebuilding daily metrics from raw data…"):
            result = metrics_service.recompute_daily_metrics()
        if result.get("ok"):
            st.success(
                f"Recomputed {result['daily_metrics']} days, {result['workouts']} workouts."
            )
        else:
            st.error(f"Recompute failed: {result.get('error')}. See the Debug tab.")
