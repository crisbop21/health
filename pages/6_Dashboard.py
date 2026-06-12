"""History dashboard: a glanceable snapshot of the latest readings, trend
charts with rolling averages, and training volume. Reads only through
dashboard_service; all charting/formatting is presentation-only here."""

import altair as alt
import pandas as pd
import streamlit as st

from core import health
from core.auth import require_password
from services import dashboard_service
from services.dashboard_service import METRIC_META

require_password()

st.title("Data & History")
st.caption("Your latest readings, how they're trending, and training volume.")

if not health.db_available():
    st.error("Database unavailable — history can't be loaded right now.")
    st.stop()


# --- Cached reads: switching the period shouldn't refetch everything ------
@st.cache_data(ttl=300, show_spinner=False)
def _overview():
    return dashboard_service.overview()


@st.cache_data(ttl=300, show_spinner=False)
def _snapshot():
    return dashboard_service.snapshot()


@st.cache_data(ttl=300, show_spinner=False)
def _metrics(days):
    return dashboard_service.metrics_series(days=days)


@st.cache_data(ttl=300, show_spinner=False)
def _workouts(days):
    return dashboard_service.workouts_series(days=days)


# --- Controls -------------------------------------------------------------
PERIODS = {"30d": 30, "90d": 90, "6mo": 180, "1yr": 365, "2yr": 730, "All": None}
ctrl_l, ctrl_r = st.columns([4, 1])
with ctrl_l:
    period = st.segmented_control(
        "Period", list(PERIODS), default="90d", help="Window for the charts below."
    ) or "90d"
with ctrl_r:
    st.write("")
    if st.button("↻ Refresh", help="Reload data from the database."):
        st.cache_data.clear()
        st.rerun()
days = PERIODS[period]

overview = _overview()
if not overview.get("ok"):
    st.error(f"Couldn't load history: {overview.get('error')}. See the Debug tab.")
    st.stop()

m, w = overview["metrics"], overview["workouts"]
if m["days"] == 0 and w["count"] == 0:
    st.info(
        "No derived data yet. Run a **Historical backfill** on the Settings "
        "page (it recomputes metrics automatically) and your history will "
        "appear here."
    )
    st.stop()


# --- Latest snapshot (KPI cards) ------------------------------------------
st.subheader("Latest snapshot")
snap = _snapshot()
snap_metrics = snap.get("metrics", {}) if snap.get("ok") else {}
cols = st.columns(len(METRIC_META))
for col, (field, meta) in zip(cols, METRIC_META.items()):
    s = snap_metrics.get(field, {})
    latest = s.get("latest")
    unit = meta["unit"]
    value = f"{latest:g}{(' ' + unit) if unit else ''}" if latest is not None else "—"
    delta = s.get("delta")
    delta_str = f"{delta:+g}" if delta else None
    # Lower-is-better metrics (resting HR) invert the green/red; strain is neutral.
    if meta["higher_better"] is None:
        delta_color = "off"
    elif meta["higher_better"]:
        delta_color = "normal"
    else:
        delta_color = "inverse"
    col.metric(meta["label"], value, delta=delta_str, delta_color=delta_color,
               help="vs. prior 7-day average")
as_of = next((s.get("date") for s in snap_metrics.values() if s.get("date")), None)
if as_of:
    st.caption(f"As of {as_of} · arrows compare to the previous 7-day average.")


# --- Trends ---------------------------------------------------------------
raw = _metrics(days)
df = pd.DataFrame(raw)
if not df.empty:
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()


def _trend_chart(col: str, title: str, color: str, bands=None, rule=None):
    """Daily points + a 7-day rolling-average line, with optional zone bands
    (list of (low, high, color)) and a reference rule value."""
    if df.empty or col not in df or not df[col].notna().any():
        st.caption(f"No {title.lower()} data in this window.")
        return
    d = df[[col]].dropna().reset_index()
    d["roll"] = d[col].rolling(7, min_periods=1).mean()

    layers = []
    if bands:
        for low, high, c in bands:
            layers.append(
                alt.Chart(pd.DataFrame({"low": [low], "high": [high]}))
                .mark_rect(opacity=0.07, color=c)
                .encode(y="low:Q", y2="high:Q")
            )
    if rule is not None:
        layers.append(
            alt.Chart(pd.DataFrame({"y": [rule]}))
            .mark_rule(strokeDash=[4, 4], color="gray")
            .encode(y="y:Q")
        )
    points = (
        alt.Chart(d).mark_circle(size=18, opacity=0.35, color=color)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y(f"{col}:Q", title=title, scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("date:T"), alt.Tooltip(f"{col}:Q", title=title, format=".1f")],
        )
    )
    line = (
        alt.Chart(d).mark_line(color=color, strokeWidth=2.5)
        .encode(x="date:T", y="roll:Q",
                tooltip=[alt.Tooltip("date:T"), alt.Tooltip("roll:Q", title="7-day avg", format=".1f")])
    )
    st.altair_chart(alt.layer(*layers, points, line).properties(height=200), use_container_width=True)
    vals = d[col]
    st.caption(f"avg {vals.mean():.1f} · min {vals.min():.1f} · max {vals.max():.1f} · {len(vals)} days · solid line = 7-day avg")


st.subheader("Trends")
tab_rec, tab_sleep, tab_train = st.tabs(["Recovery & HRV", "Sleep", "Training load"])

with tab_rec:
    _trend_chart("recovery_score", "Recovery", "#2e7d32",
                 bands=[(0, 33, "red"), (33, 66, "orange"), (66, 100, "green")])
    c1, c2 = st.columns(2)
    with c1:
        _trend_chart("hrv_ms", "HRV (ms)", "#1565c0")
    with c2:
        _trend_chart("resting_hr", "Resting HR (bpm)", "#c62828")

with tab_sleep:
    _trend_chart("sleep_hours", "Sleep (hours)", "#6a1b9a", rule=8)
    st.caption("Dashed line marks an 8-hour reference.")

with tab_train:
    _trend_chart("strain", "Strain", "#ef6c00")


# --- Training volume ------------------------------------------------------
st.subheader("Training volume")
wrows = _workouts(days)
if wrows:
    wdf = pd.DataFrame(wrows)
    wdf["date"] = pd.to_datetime(wdf["date"])

    vol_l, vol_r = st.columns([3, 2])
    with vol_l:
        if "distance_km" in wdf:
            weekly = (
                wdf.set_index("date")["distance_km"].fillna(0).resample("W").sum()
                .reset_index()
            )
            chart = (
                alt.Chart(weekly).mark_bar(color="#00897b")
                .encode(
                    x=alt.X("date:T", title=None),
                    y=alt.Y("distance_km:Q", title="km / week"),
                    tooltip=[alt.Tooltip("date:T", title="week of"),
                             alt.Tooltip("distance_km:Q", title="km", format=".1f")],
                )
                .properties(height=220)
            )
            st.caption("Weekly distance")
            st.altair_chart(chart, use_container_width=True)
    with vol_r:
        if "sport" in wdf and wdf["sport"].notna().any():
            mix = wdf["sport"].fillna("unknown").value_counts().reset_index()
            mix.columns = ["sport", "count"]
            pie = (
                alt.Chart(mix).mark_arc(innerRadius=45)
                .encode(theta="count:Q", color=alt.Color("sport:N", legend=alt.Legend(orient="bottom")),
                        tooltip=["sport:N", "count:Q"])
                .properties(height=220)
            )
            st.caption("Sport mix")
            st.altair_chart(pie, use_container_width=True)

    recent = wdf.sort_values("date", ascending=False).head(15).copy()
    recent["date"] = recent["date"].dt.date
    if "duration_seconds" in recent:
        recent["min"] = (recent["duration_seconds"] / 60).round(0)
    show = [c for c in ("date", "sport", "distance_km", "min", "avg_hr", "max_hr") if c in recent]
    with st.expander(f"Recent workouts ({len(wdf)} in period)", expanded=False):
        st.dataframe(recent[show], hide_index=True, width="stretch")
else:
    st.caption("No workouts in this window.")


# --- Data coverage (secondary, collapsed) ---------------------------------
with st.expander("Data coverage & sources", expanded=False):
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Days of metrics", m["days"])
    k2.metric("Date span", f"{m['span_days']} d")
    k3.metric("Workouts", w["count"])
    k4.metric("Total distance", f"{w['total_distance_km']} km")
    span = " → ".join(x for x in (m["first"], m["last"]) if x) or "—"
    st.caption(f"Metrics span: {span}")

    cov, total = m["field_coverage"], (m["days"] or 1)
    cov_rows = [
        {"Metric": META["label"], "Days with data": cov[f],
         "Coverage": round(100 * cov[f] / total)}
        for f, META in METRIC_META.items()
    ]
    st.dataframe(
        pd.DataFrame(cov_rows),
        hide_index=True, width="stretch",
        column_config={"Coverage": st.column_config.ProgressColumn(
            "Coverage", format="%d%%", min_value=0, max_value=100)},
    )
    src_bits = []
    for name, dct in (("HRV", m["source_hrv"]), ("Sleep", m["source_sleep"])):
        if dct:
            src_bits.append(f"{name}: " + ", ".join(f"{k} {v}" for k, v in dct.items()))
    if src_bits:
        st.caption("Source split — " + " · ".join(src_bits))
