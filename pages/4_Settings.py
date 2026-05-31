import secrets
from datetime import date, datetime, time

import streamlit as st

from clients import whoop_client
from core import health, pace_zones
from core.auth import require_password
from repositories import garmin_raw_repo, goals_repo, whoop_raw_repo
from services import metrics_service, sync_service


def _secs_to_hms(seconds) -> tuple[int, int, int]:
    s = int(seconds or 0)
    return s // 3600, (s % 3600) // 60, s % 60


def _parse_window(value: str) -> time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except (ValueError, TypeError):
        return time(6, 0)

require_password()

st.title("Settings")

if not health.db_available():
    st.error(
        "Database unavailable. Reads will fail and writes are disabled until "
        "Supabase is reachable."
    )

# --- Whoop OAuth callback: handle ?code=... when Whoop redirects back here ---
if "code" in st.query_params:
    code = st.query_params["code"]
    try:
        whoop_client.exchange_code(code)
        st.query_params.clear()
        st.success("Whoop connected.")
    except Exception as exc:
        st.error(f"Whoop authorization failed: {exc}")

st.subheader("Goal")
try:
    goal = goals_repo.get_active() or {}
except Exception as exc:
    goal = {}
    st.error(f"Could not load the goal: {exc}")

g_h, g_m, g_s = _secs_to_hms(goal.get("goal_time_seconds"))
windows = (goal.get("time_windows") or {}).get("default") or ["06:00", "08:00"]
blackout_default = "\n".join(b for b in (goal.get("blackout_dates") or []) if isinstance(b, str))

with st.form("goal_editor"):
    sport = st.text_input("Sport", value=goal.get("sport") or "running")
    try:
        race_default = date.fromisoformat(goal["race_date"]) if goal.get("race_date") else date(2026, 12, 6)
    except (ValueError, KeyError):
        race_default = date(2026, 12, 6)
    race_date = st.date_input("Race date", value=race_default)

    st.markdown("Goal finish time")
    t1, t2, t3 = st.columns(3)
    hours = t1.number_input("h", min_value=0, max_value=99, value=int(g_h))
    minutes = t2.number_input("m", min_value=0, max_value=59, value=int(g_m))
    seconds = t3.number_input("s", min_value=0, max_value=59, value=int(g_s))

    c1, c2 = st.columns(2)
    days_per_week = c1.number_input("Training days / week", min_value=1, max_value=7, value=int(goal.get("days_per_week") or 5))
    max_session = c2.number_input("Max session (min)", min_value=15, max_value=600, value=int(goal.get("max_session_minutes") or 120))

    w1, w2 = st.columns(2)
    win_start = w1.time_input("Window start", value=_parse_window(windows[0]))
    win_end = w2.time_input("Window end", value=_parse_window(windows[-1]))

    blackout_text = st.text_area(
        "Blackout dates (one ISO date per line)", value=blackout_default, placeholder="2026-07-04"
    )

    if st.form_submit_button("Save goal", type="primary"):
        blackouts = [line.strip() for line in blackout_text.splitlines() if line.strip()]
        new_goal = {
            "sport": sport.strip() or "running",
            "race_date": race_date.isoformat(),
            "goal_time_seconds": int(hours) * 3600 + int(minutes) * 60 + int(seconds),
            "days_per_week": int(days_per_week),
            "max_session_minutes": int(max_session),
            "time_windows": {"default": [win_start.strftime("%H:%M"), win_end.strftime("%H:%M")]},
            "blackout_dates": blackouts,
        }
        try:
            goals_repo.create(new_goal)
            st.success("Goal saved.")
            st.rerun()
        except Exception as exc:
            st.error(f"Could not save the goal: {exc}")

if goal.get("goal_time_seconds") and (goal.get("sport") or "running") == "running":
    zones = pace_zones.pace_zones_formatted(goal["goal_time_seconds"])
    st.caption("Pace zones: " + " · ".join(f"{z} {p}" for z, p in zones.items()))

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
