"""Setup checklist: which onboarding steps are done, so a fresh install
explains itself instead of requiring tribal knowledge. Each probe is
failure-tolerant — an unreachable dependency just reads as "not done"."""

from __future__ import annotations

from repositories import goals_repo
from services import dashboard_service, plan_service, sync_service

# Days of derived metrics that count as "history is in".
_HISTORY_MIN_DAYS = 30


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def status() -> dict:
    """Ordered steps with done flags and hints; complete=True once all pass."""
    devices = _safe(sync_service.device_status) or {}
    garmin = devices.get("garmin") or {}
    whoop = devices.get("whoop") or {}
    overview = _safe(dashboard_service.overview) or {}
    metric_days = (overview.get("metrics") or {}).get("days", 0) if overview.get("ok") else 0
    goal = _safe(goals_repo.get_active)
    plan_rows = (_safe(plan_service.current_plan) or {}).get("rows") or []

    steps = [
        {
            "key": "whoop",
            "label": "Connect Whoop",
            "done": bool(whoop.get("connected")),
            "hint": "Settings → Connect Whoop (OAuth).",
        },
        {
            "key": "garmin",
            "label": "Connect Garmin",
            "done": bool(garmin.get("rows")),
            "hint": "Mint a token locally with `python -m scripts.garmin_login`, then sync.",
        },
        {
            "key": "history",
            "label": "Backfill your history",
            "done": metric_days >= _HISTORY_MIN_DAYS,
            "hint": "Settings → Historical backfill (pulls past months and builds metrics).",
        },
        {
            "key": "goal",
            "label": "Set your race goal",
            "done": bool(goal),
            "hint": "Settings → Goal: race date, distance, and target time.",
        },
        {
            "key": "plan",
            "label": "Generate a training plan",
            "done": bool(plan_rows),
            "hint": "Plan → Generate plan.",
        },
    ]
    return {"ok": True, "steps": steps, "complete": all(s["done"] for s in steps)}
