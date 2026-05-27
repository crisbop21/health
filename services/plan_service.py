"""Training plan orchestration. Reads the active goal, asks Claude for a plan,
writes the plan rows and an audit revision. Pure Python — no Streamlit."""

from __future__ import annotations

from clients import claude_client
from core import logger
from repositories import goals_repo, plan_revisions_repo, training_plan_repo


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


def generate_initial_plan(goal_id: str | None = None, recent_metrics: dict | None = None) -> dict:
    """Generate the first plan for a goal. Returns a summary dict."""
    goal = goals_repo.get(goal_id) if goal_id else goals_repo.get_active()
    if not goal:
        logger.error("claude", "generate_initial_plan: no active goal")
        return {"ok": False, "error": "No active goal configured."}

    try:
        result = claude_client.generate_plan(goal, recent_metrics or {})
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    version = training_plan_repo.next_version()
    rows = _plan_rows_from_result(result, version)
    count = training_plan_repo.insert_many(rows)

    plan_revisions_repo.insert(
        trigger="initial",
        claude_input={"goal": goal, "recent_metrics": recent_metrics or {}},
        claude_output=result.get("raw_output"),
        tokens_in=result.get("tokens_in"),
        tokens_out=result.get("tokens_out"),
        cost_usd=result.get("cost_usd"),
        reason="initial plan generation",
    )

    logger.info(
        "calc",
        "generate_initial_plan complete",
        {"version": version, "days": count, "cost_usd": round(result.get("cost_usd", 0), 4)},
    )
    return {
        "ok": True,
        "version": version,
        "count": count,
        "summary": result.get("summary", ""),
        "cost_usd": result.get("cost_usd"),
    }
