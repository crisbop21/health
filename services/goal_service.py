"""Goal reads for the UI: the persistent race header and anything else that
needs "what are we training for" context. Pure Python — no Streamlit. Always
returns ok=True; a missing/unreadable goal just yields empty fields so page
chrome silently disappears instead of breaking."""

from __future__ import annotations

from datetime import date

from core import clock, logger, pace_zones
from repositories import goals_repo

_DISTANCE_LABELS = {5.0: "5K", 10.0: "10K", 21.0975: "Half marathon", 42.195: "Marathon"}


def _distance_label(km: float | None) -> str | None:
    if not km:
        return None
    for d, label in _DISTANCE_LABELS.items():
        if abs(km - d) < 0.3:
            return label
    return f"{km:g} km"


def race_summary() -> dict:
    """The header line's ingredients: race date, countdown, goal time, sport,
    and distance label."""
    try:
        goal = goals_repo.get_active()
    except Exception as exc:
        logger.warning("calc", "race_summary: goal unavailable", {"error": str(exc)})
        goal = None

    if not goal or not goal.get("race_date"):
        return {"ok": True, "race_date": None}

    try:
        days = (date.fromisoformat(goal["race_date"]) - clock.local_today()).days
    except ValueError:
        days = None

    distance_km = goal.get("race_distance_km") or pace_zones.MARATHON_KM
    return {
        "ok": True,
        "race_date": goal["race_date"],
        "days_to_race": days,
        "weeks_to_race": days // 7 if days is not None and days >= 0 else None,
        "sport": goal.get("sport") or "running",
        "goal_time_seconds": goal.get("goal_time_seconds"),
        "goal_time": pace_zones.format_duration(goal.get("goal_time_seconds")),
        "race_distance_km": distance_km,
        "distance_label": _distance_label(distance_km),
    }
