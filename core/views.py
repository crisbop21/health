"""The Today decision screen, shared by the home page (the app's landing view)
and pages/1_Today.py. Layout answers the runner's three questions in order:
am I ready (verdict banner), what's the session (plan + status), and am I on
track (projections; expanded during race week)."""

from __future__ import annotations

from datetime import timedelta

import streamlit as st

from core import clock, pace_zones, ui
from services import (
    benchmark_service,
    log_service,
    onboarding_service,
    qa_service,
    readiness_service,
    test_service,
)

_VERDICT = {
    "green": (st.success, "Good to go — train as planned."),
    "amber": (st.warning, "Proceed with care — keep today honest-easy if in doubt."),
    "red": (st.error, "Back off — today is for recovery."),
    "unknown": (st.info, "No readiness verdict yet."),
}


def _onboarding_checklist() -> None:
    status = onboarding_service.status()
    if not status.get("ok") or status.get("complete"):
        return
    with st.container(border=True):
        st.markdown("**Finish setting up** — each step unlocks more of the app:")
        for s in status["steps"]:
            if s["done"]:
                st.markdown(f"✅ ~~{s['label']}~~")
            else:
                st.markdown(f"⬜ **{s['label']}** — {s['hint']}")


def _readiness_banner() -> None:
    r = readiness_service.readiness()
    render, headline = _VERDICT[r["verdict"]]
    body = f"**{headline}**"
    if r["reasons"]:
        body += "\n\n" + "\n".join(f"- {reason}" for reason in r["reasons"])
    render(body)
    m = r["metrics"]
    if any(v is not None for v in m.values()):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Recovery", f"{m['recovery_score']:.0f}" if m["recovery_score"] is not None else "—")
        c2.metric("Sleep", f"{m['sleep_hours']:.1f} h" if m["sleep_hours"] is not None else "—")
        c3.metric("HRV", f"{m['hrv_ms']:.0f} ms" if m["hrv_ms"] is not None else "—")
        c4.metric("Load (ACWR)", f"{m['acwr']:.2f}" if m["acwr"] is not None else "—",
                  help="7-day vs 28-day distance load. 0.8–1.3 is the sweet spot.")


def _projection_cards(title: str = "If race day were today") -> None:
    proj = benchmark_service.race_projections()
    if not proj.get("ok"):
        return
    rows = [p for p in proj["projections"] if p.get("projected_seconds")]
    if not rows:
        st.caption("Race projections appear once you have runs of 5 km or more synced.")
        return
    st.markdown(f"**{title}**")
    cols = st.columns(len(rows))
    for col, p in zip(cols, rows):
        delta = None
        if p.get("delta_seconds") is not None:
            sign = "+" if p["delta_seconds"] >= 0 else "-"
            delta = f"{sign}{pace_zones.format_duration(abs(p['delta_seconds']))} vs goal"
        # Slower than goal (positive delta) should read red -> inverse colors.
        col.metric(p["label"], p["projected"], delta=delta, delta_color="inverse")
        src = p.get("source") or {}
        col.caption(
            f"{p['confidence']} confidence · from {src.get('distance_km', '?')} km "
            f"on {src.get('date', '?')}"
        )
    st.caption(
        f"Riegel projections from your best efforts in the last "
        f"{proj['window_days']} days ({proj['runs_considered']} qualifying runs)."
    )


def _race_week_mode() -> None:
    taper = readiness_service.taper_status()
    if not taper.get("race_week"):
        return
    days = taper["days_to_race"]
    headline = "🏁 **Race day!**" if days == 0 else f"🏁 **Race week — {days} day(s) to go.**"
    if taper.get("tapering") is True:
        st.info(f"{headline} Load is tapering nicely — keep the legs fresh.")
    elif taper.get("tapering") is False:
        st.warning(
            f"{headline} Your acute load is still above your chronic base — "
            "cut volume now so you arrive fresh."
        )
    else:
        st.info(headline)


def render_today() -> None:
    st.title("Today")
    ui.race_header()
    today = clock.local_today().isoformat()

    _onboarding_checklist()
    _race_week_mode()
    _readiness_banner()

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
            st.markdown(
                f"**{item.get('planned_workout_type', '—')}** · {item.get('intensity_zone', '')}"
            )
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
        st.subheader("This week's tests")
        week_end = (clock.local_today() + timedelta(days=7)).isoformat()
        tests = test_service.upcoming_tests(today, week_end).get("rows", [])
        if tests:
            for t in tests:
                flag = "done" if t.get("completed") else "scheduled"
                st.write(
                    f"- {t.get('scheduled_date')}: **{t.get('test_type')}** ({flag}) — "
                    f"{t.get('target_metric')}"
                )
        else:
            st.caption("No progress tests scheduled this week.")

    st.divider()
    _projection_cards()

    errors = log_service.recent_logs(limit=3, severity="error").get("rows", [])
    if errors:
        with st.expander(f"Recent errors ({len(errors)})", expanded=False):
            for e in errors:
                when = (e.get("event_at") or "")[:19].replace("T", " ")
                st.warning(f"{when} · [{e.get('source')}] {e.get('message')}")
