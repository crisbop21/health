"""Progress-test scheduling and result logging. Claude picks the tests; the
athlete logs the results. Pure Python — no Streamlit."""

from __future__ import annotations

from typing import Any

from clients import claude_client
from core import clock, logger
from repositories import goals_repo, progress_tests_repo, training_plan_repo


def schedule_progress_tests() -> dict:
    """Ask Claude to place 3-5 progress tests across the current plan window,
    replacing any pending (not-yet-completed) tests."""
    goal = goals_repo.get_active()
    if not goal:
        return {"ok": False, "error": "No active goal configured."}

    try:
        plan = training_plan_repo.get_plan()
    except Exception as exc:
        return {"ok": False, "error": f"Could not load the plan: {exc}"}
    dates = [r.get("date") for r in plan if r.get("date")]
    if not dates:
        return {"ok": False, "error": "No plan to schedule tests against. Generate one first."}

    today = clock.local_today().isoformat()
    window = {
        "start": max(today, min(dates)),
        "race_date": goal.get("race_date"),
        "first_plan_date": min(dates),
        "last_plan_date": max(dates),
    }

    try:
        result = claude_client.schedule_tests(goal, window)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    rows = [
        {
            "scheduled_date": t.get("scheduled_date"),
            "test_type": t.get("test_type"),
            "target_metric": t.get("target_metric"),
            "notes": t.get("notes"),
            "completed": False,
        }
        for t in result.get("tests", [])
    ]
    progress_tests_repo.delete_incomplete()
    count = progress_tests_repo.insert_many(rows)

    logger.info(
        "calc",
        "schedule_progress_tests complete",
        {"count": count, "cost_usd": round(result.get("cost_usd") or 0, 4)},
    )
    return {"ok": True, "count": count, "cost_usd": result.get("cost_usd")}


def log_result(test_id: str, result_value: Any, notes: str | None = None) -> dict:
    try:
        progress_tests_repo.mark_complete(test_id, {"result": result_value}, notes)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def all_tests() -> dict:
    """Every progress test, for the Plan page. Never raises into the UI."""
    try:
        return {"ok": True, "rows": progress_tests_repo.get_all()}
    except Exception as exc:
        logger.warning("db", "progress tests load failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc), "rows": []}


def upcoming_tests(start: str, end: str) -> dict:
    """Tests scheduled in [start, end], for the Today page. Never raises."""
    try:
        return {"ok": True, "rows": progress_tests_repo.upcoming(start, end)}
    except Exception as exc:
        logger.warning("db", "upcoming tests load failed", {"error": str(exc)})
        return {"ok": False, "error": str(exc), "rows": []}
