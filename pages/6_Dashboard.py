from datetime import date

import pandas as pd
import streamlit as st

from core import health
from core.auth import require_password
from services import dashboard_service

require_password()

st.title("Data & History")
st.caption("What historical data you have, and how your metrics have evolved.")

if not health.db_available():
    st.error("Database unavailable — history can't be loaded right now.")
    st.stop()

window = st.slider(
    "Window (days)", min_value=30, max_value=730, value=365, step=5,
    help="How far back the charts and tables below reach.",
)

# --- Coverage: what data exists -------------------------------------------
overview = dashboard_service.overview()
if not overview.get("ok"):
    st.error(f"Couldn't summarize history: {overview.get('error')}. See the Debug tab.")
    st.stop()

m, w = overview["metrics"], overview["workouts"]

if m["days"] == 0 and w["count"] == 0:
    st.warning(
        "No derived data yet. Backfill your devices in **Settings**, then run "
        "**Recompute metrics**."
    )
    st.stop()

st.subheader("Coverage")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Days of metrics", m["days"])
c2.metric("Date span", f"{m['span_days']} d")
c3.metric("Workouts", w["count"])
c4.metric("Total distance", f"{w['total_distance_km']} km")
span = " → ".join(x for x in (m["first"], m["last"]) if x) or "—"
st.caption(f"Metrics span: {span}")

# Per-field coverage: how many days actually carry each metric, and its source.
cov = m["field_coverage"]
total = m["days"] or 1
labels = {
    "hrv_ms": "HRV", "resting_hr": "Resting HR", "sleep_hours": "Sleep",
    "recovery_score": "Recovery", "strain": "Strain",
}
cov_rows = [
    {"Metric": labels[f], "Days": cov[f], "Coverage": f"{round(100 * cov[f] / total)}%"}
    for f in labels
]
st.dataframe(pd.DataFrame(cov_rows), hide_index=True, use_container_width=True)

src_bits = []
for name, d in (("HRV", m["source_hrv"]), ("Sleep", m["source_sleep"])):
    if d:
        src_bits.append(f"{name}: " + ", ".join(f"{k} {v}" for k, v in d.items()))
if src_bits:
    st.caption("Source split — " + " · ".join(src_bits))

# --- Evolution: metric time series ----------------------------------------
st.subheader("Metric evolution")
metrics = dashboard_service.metrics_series(days=window)
if metrics:
    df = pd.DataFrame(metrics)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    charts = [
        ("hrv_ms", "HRV (ms)"),
        ("resting_hr", "Resting HR (bpm)"),
        ("sleep_hours", "Sleep (hours)"),
        ("recovery_score", "Recovery score"),
        ("strain", "Strain"),
    ]
    for col, title in charts:
        if col in df and df[col].notna().any():
            st.caption(title)
            st.line_chart(df[col], height=180)
else:
    st.caption("No metrics in this window.")

# --- Workouts -------------------------------------------------------------
st.subheader("Training volume")
workouts = dashboard_service.workouts_series(days=window)
if workouts:
    wdf = pd.DataFrame(workouts)
    wdf["date"] = pd.to_datetime(wdf["date"])
    if "distance_km" in wdf:
        weekly = (
            wdf.set_index("date")["distance_km"].fillna(0).resample("W").sum()
        )
        st.caption("Weekly distance (km)")
        st.bar_chart(weekly, height=200)

    recent = (
        wdf.sort_values("date", ascending=False)
        .head(20)[[c for c in ("date", "sport", "distance_km", "duration_seconds", "avg_hr") if c in wdf]]
        .copy()
    )
    recent["date"] = recent["date"].dt.date
    if "duration_seconds" in recent:
        recent["duration_min"] = (recent["duration_seconds"] / 60).round(0)
        recent = recent.drop(columns=["duration_seconds"])
    st.caption("Recent workouts")
    st.dataframe(recent, hide_index=True, use_container_width=True)
else:
    st.caption("No workouts in this window.")
