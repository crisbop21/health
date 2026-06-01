"""Read-only summaries for the history dashboard. Answers two questions:
"what historical data do we actually have?" (coverage) and "how has it evolved?"
(time series). Pure reads from the derived tables; never writes."""

from __future__ import annotations

from datetime import date, timedelta

from core import logger
from repositories import daily_metrics_repo, workouts_repo

# Derived rows never predate device history; a fixed floor keeps the "all data"
# range query simple without a dedicated min-date endpoint.
_EPOCH = "2000-01-01"

# daily_metrics fields worth reporting coverage on, in display order.
_METRIC_FIELDS = ("hrv_ms", "resting_hr", "sleep_hours", "recovery_score", "strain")


def _today() -> str:
    return date.today().isoformat()


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


def metrics_series(days: int = 365) -> list[dict]:
    """daily_metrics rows over the last `days`, oldest first."""
    start = (date.today() - timedelta(days=days)).isoformat()
    return daily_metrics_repo.get_range(start, _today())


def workouts_series(days: int = 365) -> list[dict]:
    """workout rows over the last `days`, oldest first."""
    start = (date.today() - timedelta(days=days)).isoformat()
    return workouts_repo.get_range(start, _today())
