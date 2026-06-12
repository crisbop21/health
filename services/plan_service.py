"""Training plan orchestration. Reads the active goal and recent metrics, asks
Claude for a plan, runs guardrail checks, and writes the plan rows plus an
audit revision. Pure Python — no Streamlit."""

from __future__ import annotations

from datetime import date, timedelta

from clients import claude_client
from core import clock, guardrails, logger, pace_zones
from repositories import (
    daily_metrics_repo,
    goals_repo,
    plan_revisions_repo,
    training_plan_repo,
    workouts_repo,
)


def _recent_metrics(days: int = 14) -> list:
    try:
        return daily_metrics_repo.get_recent(days)
    except Exception as exc:
        logger.warning("calc", "could not load recent metrics", {"error": str(exc)})
        return []


def _plan_rows_from_result(result: dict, version: int) -> list[dict]:
    rows = []
    for item in result.get("plan", []):
        rows.append(
            {
                "date": item.get("date"),
                "planned_sport": item.get("planned_sport"),
                "planned_workout_type": item.get("planned_workout_type"),
                "planned_distance_km": item.get("planned_distance_km"),
                "planned_duration_minutes": item.get("planned_duration_minutes"),
                "planned_pace": item.get("planned_pace"),
                "intensity_zone": item.get("intensity_zone"),
                "notes": item.get("notes"),
                "version": version,
            }
        )
    return rows


def _run_guardrails(plan_items: list[dict], goal: dict) -> None:
    for warning in guardrails.check_plan(plan_items, goal):
        logger.warning("calc", f"guardrail: {warning['message']}", warning)


def _persist(result: dict, goal: dict, trigger: str, reason: str, recent_metrics) -> dict:
    version = training_plan_repo.next_version()
    rows = _plan_rows_from_result(result, version)
    count = training_plan_repo.insert_many(rows)

    _run_guardrails(result.get("plan", []), goal)

    plan_revisions_repo.insert(
        trigger=trigger,
        claude_input={"goal": goal, "recent_metrics": recent_metrics or {}},
        claude_output=result.get("raw_output"),
        tokens_in=result.get("tokens_in"),
        tokens_out=result.get("tokens_out"),
        cost_usd=result.get("cost_usd"),
        reason=reason,
    )

    logger.info(
        "calc",
        f"{trigger} plan persisted",
        {"version": version, "days": count, "cost_usd": round(result.get("cost_usd") or 0, 4)},
    )
    return {
        "ok": True,
        "version": version,
        "count": count,
        "summary": result.get("summary", ""),
        "cost_usd": result.get("cost_usd"),
    }


def generate_initial_plan(goal_id: str | None = None, recent_metrics=None) -> dict:
    """Generate the first plan for a goal."""
    goal = goals_repo.get(goal_id) if goal_id else goals_repo.get_active()
    if not goal:
        logger.error("claude", "generate_initial_plan: no active goal")
        return {"ok": False, "error": "No active goal configured."}

    metrics = recent_metrics if recent_metrics is not None else _recent_metrics()
    zones = pace_zones.pace_zones(goal.get("goal_time_seconds"), goal.get("sport", "running"))

    try:
        result = claude_client.generate_plan(goal, metrics, zones)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    return _persist(result, goal, trigger="initial", reason="initial plan generation", recent_metrics=metrics)


def recalibrate_plan(reason: str = "manual recalibration", recent_metrics=None) -> dict:
    """Regenerate the remaining plan from today onward based on recent metrics."""
    goal = goals_repo.get_active()
    if not goal:
        logger.error("claude", "recalibrate_plan: no active goal")
        return {"ok": False, "error": "No active goal configured."}

    try:
        latest = training_plan_repo.get_plan()
    except Exception as exc:
        return {"ok": False, "error": f"Could not load current plan: {exc}"}
    today = clock.local_today().isoformat()
    current_remaining = [r for r in latest if (r.get("date") or "") >= today]
    if not current_remaining:
        return {"ok": False, "error": "No current plan to recalibrate. Generate one first."}

    metrics = recent_metrics if recent_metrics is not None else _recent_metrics()
    zones = pace_zones.pace_zones(goal.get("goal_time_seconds"), goal.get("sport", "running"))

    try:
        result = claude_client.recalibrate_plan(
            goal, current_remaining, metrics, zones, reason
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    return _persist(result, goal, trigger="recalibration", reason=reason, recent_metrics=metrics)


def current_plan() -> dict:
    """The latest plan's rows for the Plan page. Never raises into the UI."""
    try:
        return {"ok": True, "rows": training_plan_repo.get_plan()}
    except Exception as exc:
        logger.warning("db", "plan load failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc), "rows": []}


def adherence(weeks: int = 8) -> dict:
    """Planned vs actual over the last `weeks`: weekly km comparison, training
    days hit, and which plan dates have a matching workout. Future plan days
    are excluded — adherence only judges days that have already happened."""
    try:
        today = clock.local_today()
        start = today - timedelta(days=weeks * 7)
        plan = training_plan_repo.get_plan()
        workouts = workouts_repo.get_range(start.isoformat(), today.isoformat())
    except Exception as exc:
        logger.error("calc", "adherence failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc)}

    def _week_of(iso: str) -> str:
        d = date.fromisoformat(iso)
        return (d - timedelta(days=d.weekday())).isoformat()

    today_iso = today.isoformat()
    past_plan = [
        r for r in plan
        if r.get("date") and start.isoformat() <= r["date"] <= today_iso
    ]
    workout_dates = {w["date"] for w in workouts if w.get("date")}

    weekly: dict[str, dict] = {}
    for r in past_plan:
        wk = weekly.setdefault(
            _week_of(r["date"]),
            {"planned_km": 0.0, "actual_km": 0.0, "planned_days": 0, "active_days": set()},
        )
        wk["planned_km"] += float(r.get("planned_distance_km") or 0)
        if r.get("planned_distance_km") or r.get("planned_duration_minutes"):
            wk["planned_days"] += 1
    for w in workouts:
        d = w.get("date")
        if not d:
            continue
        wk = weekly.setdefault(
            _week_of(d),
            {"planned_km": 0.0, "actual_km": 0.0, "planned_days": 0, "active_days": set()},
        )
        wk["actual_km"] += float(w.get("distance_km") or 0)
        wk["active_days"].add(d)

    rows = [
        {
            "week": week,
            "planned_km": round(v["planned_km"], 1),
            "actual_km": round(v["actual_km"], 1),
            "planned_days": v["planned_days"],
            "active_days": len(v["active_days"]),
        }
        for week, v in sorted(weekly.items())
    ]
    planned_km = round(sum(r["planned_km"] for r in rows), 1)
    actual_km = round(sum(r["actual_km"] for r in rows), 1)
    return {
        "ok": True,
        "weeks": rows,
        "planned_km": planned_km,
        "actual_km": actual_km,
        "adherence_pct": int(round(100 * actual_km / planned_km)) if planned_km else None,
        "completed_dates": sorted(workout_dates),
    }
