"""Read-only summaries for the history dashboard. Answers two questions:
"what historical data do we actually have?" (coverage) and "how has it evolved?"
(time series). Pure reads from the derived tables; never writes."""

from __future__ import annotations

from datetime import date, timedelta

from core import clock, logger
from repositories import daily_metrics_repo, workouts_repo

# Derived rows never predate device history; a fixed floor keeps the "all data"
# range query simple without a dedicated min-date endpoint.
_EPOCH = "2000-01-01"

# daily_metrics fields worth reporting on, in display order, with the metadata
# the UI needs: label, unit, and trend direction (True = higher is better,
# False = lower is better, None = neutral/load metric).
METRIC_META: dict[str, dict] = {
    "hrv_ms": {"label": "HRV", "unit": "ms", "higher_better": True},
    "resting_hr": {"label": "Resting HR", "unit": "bpm", "higher_better": False},
    "sleep_hours": {"label": "Sleep", "unit": "h", "higher_better": True},
    "recovery_score": {"label": "Recovery", "unit": "", "higher_better": True},
    "strain": {"label": "Strain", "unit": "", "higher_better": None},
}
_METRIC_FIELDS = tuple(METRIC_META)


def _today() -> str:
    return clock.local_today().isoformat()


def _span_days(first: str | None, last: str | None) -> int:
    if not first or not last:
        return 0
    return (date.fromisoformat(last) - date.fromisoformat(first)).days + 1


def overview() -> dict:
    """Summarize what historical data exists: date span, day count, per-field
    coverage, and workout totals. ok=False with an error on failure."""
    try:
        metrics = daily_metrics_repo.get_range(_EPOCH, _today())
        workouts = workouts_repo.get_range(_EPOCH, _today())

        m_dates = [m["date"] for m in metrics if m.get("date")]
        m_first, m_last = (min(m_dates), max(m_dates)) if m_dates else (None, None)
        field_coverage = {
            f: sum(1 for m in metrics if m.get(f) is not None) for f in _METRIC_FIELDS
        }
        source_hrv = _count_by(metrics, "source_hrv")
        source_sleep = _count_by(metrics, "source_sleep")

        w_dates = [w["date"] for w in workouts if w.get("date")]
        w_first, w_last = (min(w_dates), max(w_dates)) if w_dates else (None, None)
        total_km = round(sum(w.get("distance_km") or 0 for w in workouts), 1)
        by_sport = _count_by(workouts, "sport")

        return {
            "ok": True,
            "metrics": {
                "days": len(metrics),
                "first": m_first,
                "last": m_last,
                "span_days": _span_days(m_first, m_last),
                "field_coverage": field_coverage,
                "source_hrv": source_hrv,
                "source_sleep": source_sleep,
            },
            "workouts": {
                "count": len(workouts),
                "first": w_first,
                "last": w_last,
                "total_distance_km": total_km,
                "by_sport": by_sport,
            },
        }
    except Exception as exc:
        logger.error("calc", "dashboard overview failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc)}


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        v = r.get(key)
        if v:
            out[v] = out.get(v, 0) + 1
    return out


def snapshot() -> dict:
    """Latest value of each metric and its change vs the prior 7-day average,
    for the KPI cards. ok=False with an error on failure."""
    try:
        rows = daily_metrics_repo.get_range(
            (clock.local_today() - timedelta(days=21)).isoformat(), _today()
        )
        out: dict[str, dict] = {}
        for field in _METRIC_FIELDS:
            series = sorted(
                (r["date"], r[field]) for r in rows
                if r.get("date") and r.get(field) is not None
            )
            if not series:
                out[field] = {"latest": None, "date": None, "delta": None}
                continue
            latest_date, latest = series[-1]
            latest_d = date.fromisoformat(latest_date)
            # Baseline: the up-to-7 days immediately before the latest reading.
            prior = [
                v for d, v in series[:-1]
                if 0 < (latest_d - date.fromisoformat(d)).days <= 7
            ]
            baseline = sum(prior) / len(prior) if prior else None
            out[field] = {
                "latest": round(float(latest), 1),
                "date": latest_date,
                "baseline": round(baseline, 1) if baseline is not None else None,
                "delta": round(float(latest) - baseline, 1) if baseline is not None else None,
            }
        return {"ok": True, "metrics": out}
    except Exception as exc:
        logger.error("calc", "dashboard snapshot failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc)}


def _window_start(days: int | None) -> str:
    """ISO start date for a rolling window; None means all history (epoch)."""
    if days is None:
        return _EPOCH
    return (clock.local_today() - timedelta(days=days)).isoformat()


def metrics_series(days: int | None = 365) -> list[dict]:
    """daily_metrics rows over the last `days` (None = everything), oldest first."""
    return daily_metrics_repo.get_range(_window_start(days), _today())


def workouts_series(days: int | None = 365) -> list[dict]:
    """workout rows over the last `days` (None = everything), oldest first."""
    return workouts_repo.get_range(_window_start(days), _today())


def training_load(days: int | None = 365) -> dict:
    """Daily distance load with acute (7-day) and chronic (28-day) rolling
    averages and their ratio (ACWR). Days without workouts count as zero load.
    The commonly cited 0.8–1.3 "sweet spot" band is drawn by the UI. Returns
    rows from the first workout in the window through today; ok=False on
    failure."""
    try:
        rows = workouts_repo.get_range(_window_start(days), _today())
        km_by_date: dict[str, float] = {}
        for w in rows:
            d = w.get("date")
            if d:
                km_by_date[d] = km_by_date.get(d, 0.0) + (w.get("distance_km") or 0.0)
        if not km_by_date:
            return {"ok": True, "rows": []}

        out: list[dict] = []
        loads: list[float] = []
        cur = date.fromisoformat(min(km_by_date))
        end = date.fromisoformat(_today())
        while cur <= end:
            iso = cur.isoformat()
            loads.append(round(km_by_date.get(iso, 0.0), 3))
            acute = sum(loads[-7:]) / min(len(loads), 7)
            chronic = sum(loads[-28:]) / min(len(loads), 28)
            out.append(
                {
                    "date": iso,
                    "load_km": loads[-1],
                    "acute": round(acute, 2),
                    "chronic": round(chronic, 2),
                    "acwr": round(acute / chronic, 2) if chronic > 0 else None,
                }
            )
            cur += timedelta(days=1)
        return {"ok": True, "rows": out}
    except Exception as exc:
        logger.error("calc", "training_load failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc)}
