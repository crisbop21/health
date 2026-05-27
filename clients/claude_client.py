"""Claude (Anthropic API) client. The only module that talks to Claude.

Uses Opus 4.7 with adaptive thinking and a JSON-schema structured output so the
plan comes back as a validated object. Streams the response because a full
race-block plan is a large output. Returns the parsed plan plus token/cost
accounting for the plan_revisions audit trail."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from core import logger
from core.config import settings

MODEL = "claude-opus-4-7"
MAX_TOKENS = 32000

# Opus 4.7 pricing, USD per token (input / output; cache write 1.25x, read 0.1x).
_PRICING = {
    "claude-opus-4-7": {
        "input": 5.0 / 1_000_000,
        "output": 25.0 / 1_000_000,
        "cache_write": 6.25 / 1_000_000,
        "cache_read": 0.5 / 1_000_000,
    }
}

_PLAN_ITEM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "date": {"type": "string"},
        "planned_sport": {"type": "string"},
        "planned_workout_type": {"type": "string"},
        "planned_distance_km": {"type": ["number", "null"]},
        "planned_duration_minutes": {"type": ["integer", "null"]},
        "planned_pace": {"type": ["string", "null"]},
        "intensity_zone": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": [
        "date",
        "planned_sport",
        "planned_workout_type",
        "planned_distance_km",
        "planned_duration_minutes",
        "planned_pace",
        "intensity_zone",
        "notes",
    ],
}

_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "plan": {"type": "array", "items": _PLAN_ITEM_SCHEMA},
    },
    "required": ["summary", "plan"],
}


@lru_cache(maxsize=8)
def _load_prompt(name: str) -> str:
    path = Path(__file__).resolve().parent.parent / "prompts" / f"{name}.md"
    return path.read_text(encoding="utf-8")


def _system_prompt() -> str:
    return _load_prompt("plan_generation")


def _estimate_cost(model: str, usage: Any) -> float:
    p = _PRICING.get(model, _PRICING[MODEL])
    return (
        getattr(usage, "input_tokens", 0) * p["input"]
        + getattr(usage, "output_tokens", 0) * p["output"]
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * p["cache_write"]
        + (getattr(usage, "cache_read_input_tokens", 0) or 0) * p["cache_read"]
    )


def _total_input_tokens(usage: Any) -> int:
    return (
        getattr(usage, "input_tokens", 0)
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        + (getattr(usage, "cache_read_input_tokens", 0) or 0)
    )


def _extract_json(message: Any) -> dict:
    import json

    for block in message.content:
        if getattr(block, "type", None) == "text":
            return json.loads(block.text)
    raise ValueError("No text block with structured output in Claude response")


def _build_user_message(
    goal: dict,
    recent_metrics,
    pace_zones: dict,
    today: str,
    current_plan: list | None = None,
    reason: str | None = None,
) -> str:
    import json

    payload = {
        "today": today,
        "mode": "recalibration" if current_plan is not None else "initial",
        "goal": {
            "sport": goal.get("sport"),
            "race_date": goal.get("race_date"),
            "goal_time_seconds": goal.get("goal_time_seconds"),
            "days_per_week": goal.get("days_per_week"),
            "max_session_minutes": goal.get("max_session_minutes"),
            "time_windows": goal.get("time_windows"),
            "blackout_dates": goal.get("blackout_dates"),
        },
        "pace_zones_sec_per_km": pace_zones or {},
        "recent_metrics": recent_metrics or {},
    }
    if current_plan is not None:
        payload["reason"] = reason
        payload["current_remaining_plan"] = current_plan

    verb = "Recalibrate" if current_plan is not None else "Generate"
    return (
        f"{verb} the training plan for this athlete.\n\nContext:\n"
        + json.dumps(payload, default=str, indent=2, sort_keys=True)
    )


def _generate(
    goal: dict,
    recent_metrics,
    pace_zones: dict,
    today: str,
    current_plan: list | None = None,
    reason: str | None = None,
) -> dict:
    """Run the structured, streamed plan request. Raises on API failure."""
    import time

    import anthropic

    user_message = _build_user_message(
        goal, recent_metrics, pace_zones, today, current_plan, reason
    )
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    started = time.monotonic()
    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": _system_prompt(),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": _PLAN_SCHEMA},
            },
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            message = stream.get_final_message()
    except Exception as exc:
        logger.error("claude", "plan request failed", {"error": str(exc)})
        raise

    data = _extract_json(message)
    cost = _estimate_cost(message.model, message.usage)
    latency_ms = round((time.monotonic() - started) * 1000)

    logger.info(
        "claude",
        "plan request succeeded",
        {
            "plan_days": len(data.get("plan", [])),
            "tokens_in": _total_input_tokens(message.usage),
            "tokens_out": message.usage.output_tokens,
            "cost_usd": round(cost, 4),
            "latency_ms": latency_ms,
            "request_id": getattr(message, "_request_id", None),
        },
    )

    return {
        "summary": data.get("summary", ""),
        "plan": data.get("plan", []),
        "tokens_in": _total_input_tokens(message.usage),
        "tokens_out": message.usage.output_tokens,
        "cost_usd": cost,
        "model": message.model,
        "raw_output": data,
    }


def generate_plan(
    goal: dict,
    recent_metrics=None,
    pace_zones: dict | None = None,
    today: str | None = None,
) -> dict:
    """Generate a full plan from today to race day."""
    return _generate(
        goal,
        recent_metrics or {},
        pace_zones or {},
        today or date.today().isoformat(),
    )


def recalibrate_plan(
    goal: dict,
    current_plan: list,
    recent_metrics=None,
    pace_zones: dict | None = None,
    reason: str | None = None,
    today: str | None = None,
) -> dict:
    """Revise the remaining plan (today onward) given recent metrics and a
    reason, preserving sound structure."""
    return _generate(
        goal,
        recent_metrics or {},
        pace_zones or {},
        today or date.today().isoformat(),
        current_plan=current_plan,
        reason=reason,
    )


_TEST_TYPES = ["5K time trial", "10K time trial", "long run benchmark", "HRV trend check"]

_PROGRESS_TESTS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "scheduled_date": {"type": "string"},
                    "test_type": {"type": "string", "enum": _TEST_TYPES},
                    "target_metric": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["scheduled_date", "test_type", "target_metric", "notes"],
            },
        }
    },
    "required": ["tests"],
}


def _first_text(message) -> str:
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def ask(question: str, context: dict) -> dict:
    """Answer a free-text question grounded in the provided context."""
    import json

    user = (
        "Context:\n"
        + json.dumps(context, default=str, sort_keys=True, indent=2)
        + f"\n\nQuestion: {question}"
    )
    try:
        message = _client().messages.create(
            model=MODEL,
            max_tokens=2000,
            system=[
                {"type": "text", "text": _load_prompt("qa"), "cache_control": {"type": "ephemeral"}}
            ],
            messages=[{"role": "user", "content": user}],
        )
    except Exception as exc:
        logger.error("claude", "ask failed", {"error": str(exc)})
        raise

    answer = _first_text(message)
    cost = _estimate_cost(message.model, message.usage)
    logger.info(
        "claude",
        "ask succeeded",
        {"tokens_out": message.usage.output_tokens, "cost_usd": round(cost, 4)},
    )
    return {
        "answer": answer,
        "tokens_in": _total_input_tokens(message.usage),
        "tokens_out": message.usage.output_tokens,
        "cost_usd": cost,
        "model": message.model,
    }


def schedule_tests(goal: dict, plan_window: dict, today: str | None = None) -> dict:
    """Pick 3-5 progress tests across the plan window. Structured output."""
    import json

    today = today or date.today().isoformat()
    payload = {"today": today, "goal": goal, "plan_window": plan_window}
    user = "Schedule progress tests for this athlete.\n\nContext:\n" + json.dumps(
        payload, default=str, sort_keys=True, indent=2
    )
    try:
        message = _client().messages.create(
            model=MODEL,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": _load_prompt("progress_tests"),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": _PROGRESS_TESTS_SCHEMA},
            },
            messages=[{"role": "user", "content": user}],
        )
    except Exception as exc:
        logger.error("claude", "schedule_tests failed", {"error": str(exc)})
        raise

    data = json.loads(_first_text(message))
    cost = _estimate_cost(message.model, message.usage)
    logger.info(
        "claude",
        "schedule_tests succeeded",
        {"count": len(data.get("tests", [])), "cost_usd": round(cost, 4)},
    )
    return {
        "tests": data.get("tests", []),
        "tokens_in": _total_input_tokens(message.usage),
        "tokens_out": message.usage.output_tokens,
        "cost_usd": cost,
        "model": message.model,
    }


def daily_status(goal: dict, today_item: dict | None, recent_metrics) -> dict:
    """One-line status for the Today page."""
    import json

    payload = {
        "today_workout": today_item or "no planned workout today",
        "last_metrics": recent_metrics or "no recent metrics",
        "goal": {"sport": goal.get("sport"), "race_date": goal.get("race_date")} if goal else {},
    }
    user = "Write today's status line.\n\nContext:\n" + json.dumps(
        payload, default=str, sort_keys=True, indent=2
    )
    try:
        message = _client().messages.create(
            model=MODEL,
            max_tokens=150,
            system=[
                {
                    "type": "text",
                    "text": _load_prompt("daily_status"),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
        )
    except Exception as exc:
        logger.error("claude", "daily_status failed", {"error": str(exc)})
        raise

    cost = _estimate_cost(message.model, message.usage)
    return {
        "status": _first_text(message).strip(),
        "cost_usd": cost,
        "model": message.model,
    }
