"""Free-text Q&A grounded in the athlete's data, and the Today status line.
Pure Python — no Streamlit."""

from __future__ import annotations

from datetime import date, timedelta

from clients import claude_client
from core import logger
from repositories import daily_metrics_repo, goals_repo, qa_log_repo, training_plan_repo


def _safe(fn, default):
    try:
        return fn()
    except Exception as exc:
        logger.warning("calc", "context load failed", {"error": str(exc)})
        return default


def _this_week_plan() -> list:
    plan = _safe(training_plan_repo.get_plan, [])
    start = date.today().isoformat()
    end = (date.today() + timedelta(days=7)).isoformat()
    return [r for r in plan if start <= (r.get("date") or "") <= end]


def ask(question: str) -> dict:
    context = {
        "goal": _safe(goals_repo.get_active, None),
        "recent_metrics": _safe(lambda: daily_metrics_repo.get_recent(7), []),
        "this_week_plan": _this_week_plan(),
    }
    try:
        result = claude_client.ask(question, context)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    try:
        qa_log_repo.insert(
            question,
            result["answer"],
            context_sent=context,
            tokens_in=result.get("tokens_in"),
            tokens_out=result.get("tokens_out"),
            cost_usd=result.get("cost_usd"),
        )
    except Exception as exc:
        logger.warning("db", "qa_log insert failed", {"error": str(exc)})

    return {"ok": True, "answer": result["answer"], "cost_usd": result.get("cost_usd")}


def daily_status() -> dict:
    goal = _safe(goals_repo.get_active, None)
    today = date.today().isoformat()
    plan = _safe(training_plan_repo.get_plan, [])
    today_item = next((r for r in plan if r.get("date") == today), None)
    metrics = _safe(lambda: daily_metrics_repo.get_recent(1), [])
    last = metrics[-1] if metrics else None

    try:
        result = claude_client.daily_status(goal, today_item, last)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "today_item": today_item, "last_metrics": last}

    return {
        "ok": True,
        "status": result["status"],
        "today_item": today_item,
        "last_metrics": last,
    }
