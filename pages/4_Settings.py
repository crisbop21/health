import secrets
from datetime import date, datetime, time

import streamlit as st

from clients import whoop_client
from core import health, pace_zones, whoop_oauth
from core.auth import require_password
from repositories import goals_repo
from services import metrics_service, sync_service


def _secs_to_hms(seconds) -> tuple[int, int, int]:
    s = int(seconds or 0)
    return s // 3600, (s % 3600) // 60, s % 60


def _parse_window(value: str) -> time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except (ValueError, TypeError):
        return time(6, 0)

# --- Whoop OAuth callback: handle ?code=... before the gate, so authorizing
# from a fresh session is never interrupted by the password form. ---
whoop_oauth.handle_callback()

require_password()

st.title("Settings")

if not health.db_available():
    st.error(
        "Database unavailable. Reads will fail and writes are disabled until "
        "Supabase is reachable."
    )

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


def _garmin_msg(g: dict) -> str:
    if not g.get("ok"):
        return f"Garmin: {g.get('error')}"
    msg = f"Garmin: {g.get('rows_written', 0)} rows"
    failed = g.get("failed_days") or 0
    if failed:
        msg += f" · {failed} day(s) skipped (rate-limited; re-run to fill)"
    return msg


def _fmt_ts(ts: str | None) -> str:
    return ts[:16].replace("T", " ") if ts else "never"


def _fmt_rows(rows) -> str:
    return f"{rows:,} raw records" if rows is not None else "row count unavailable"


def _show_sync_outcome(result: dict) -> None:
    g, w = result["garmin"], result["whoop"]
    (st.success if g.get("ok") else st.error)(_garmin_msg(g))
    (st.success if w.get("ok") else st.error)(
        f"Whoop: {w.get('rows_written', 0)} rows" if w.get("ok") else f"Whoop: {w.get('error')}"
    )


def _recompute_and_show() -> None:
    with st.spinner("Rebuilding daily metrics and workouts from raw data…"):
        result = metrics_service.recompute_daily_metrics()
    if result.get("ok"):
        st.success(f"Recomputed {result['daily_metrics']} days, {result['workouts']} workouts.")
    else:
        st.error(f"Recompute failed: {result.get('error')}. See the Debug tab.")


status = sync_service.device_status()
col_g, col_w = st.columns(2)
with col_g:
    g_status = status["garmin"]
    st.markdown("**Garmin**")
    st.caption(f"Last sync: {_fmt_ts(g_status['last_sync'])} · {_fmt_rows(g_status['rows'])}")
with col_w:
    w_status = status["whoop"]
    st.markdown("**Whoop**")
    st.caption(
        f"{'Connected' if w_status['connected'] else 'Not connected'} · "
        f"last sync: {_fmt_ts(w_status['last_sync'])} · {_fmt_rows(w_status['rows'])}"
    )
    if not w_status["connected"]:
        state = st.session_state.setdefault("whoop_oauth_state", secrets.token_urlsafe(16))
        st.link_button("Connect Whoop", whoop_client.authorize_url(state))

c1, c2 = st.columns(2)
with c1:
    if st.button(
        "Sync last 7 days",
        type="primary",
        help="Pull the last week from both devices, then rebuild the derived metrics.",
    ):
        with st.spinner("Syncing Garmin and Whoop…"):
            result = sync_service.sync_all_devices()
        _show_sync_outcome(result)
        _recompute_and_show()
with c2:
    if st.button(
        "Recompute metrics",
        help="Rebuild daily metrics and workouts by replaying the stored raw data. "
        "No device calls — safe to run any time.",
    ):
        _recompute_and_show()

st.markdown("**Historical backfill**")
st.caption(
    "Pull your full device history in one shot. Garmin's daily stats are per-day "
    "endpoints (~4 requests per day of history), so long ranges take a while — "
    "the bar tracks that loop. Garmin rate-limits bursts: skipped days are "
    "reported, and re-running fills them (backfill is idempotent). If many days "
    "skip, set `GARMIN_PACING_SECONDS` to 1-2. Metrics recompute automatically "
    "when the pull finishes."
)
BACKFILL_PRESETS = {
    "3 months": 90,
    "1 year": 365,
    "2 years": 730,
    "5 years": 1825,
    "Everything (10 years)": 3650,
}
span = st.radio("How far back?", list(BACKFILL_PRESETS), index=1, horizontal=True)
if st.button(f"Backfill {span.lower()}", type="primary"):
    days_back = BACKFILL_PRESETS[span]
    bar = st.progress(0.0, text="Starting backfill — fetching Garmin activities…")

    def _on_progress(done: int, total: int) -> None:
        bar.progress(done / total, text=f"Garmin daily stats: day {done} of {total}")

    result = sync_service.backfill_all_devices(days=days_back, on_progress=_on_progress)
    bar.empty()
    _show_sync_outcome(result)
    # Recompute even after a partial failure so whatever did land is visible.
    _recompute_and_show()
