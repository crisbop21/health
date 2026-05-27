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


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    path = Path(__file__).resolve().parent.parent / "prompts" / "plan_generation.md"
    return path.read_text(encoding="utf-8")


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


def _build_user_message(goal: dict, recent_metrics: dict, today: str) -> str:
    import json

    payload = {
        "today": today,
        "goal": {
            "sport": goal.get("sport"),
            "race_date": goal.get("race_date"),
            "goal_time_seconds": goal.get("goal_time_seconds"),
            "days_per_week": goal.get("days_per_week"),
            "max_session_minutes": goal.get("max_session_minutes"),
            "time_windows": goal.get("time_windows"),
            "blackout_dates": goal.get("blackout_dates"),
        },
        "recent_metrics": recent_metrics or {},
    }
    return (
        "Generate the training plan for this athlete.\n\nContext:\n"
        + json.dumps(payload, default=str, indent=2, sort_keys=True)
    )


def generate_plan(
    goal: dict,
    recent_metrics: dict | None = None,
    today: str | None = None,
) -> dict:
    """Generate a full plan from today to race day. Returns the parsed plan
    plus token/cost accounting. Raises on API failure (after logging)."""
    import time

    import anthropic

    today = today or date.today().isoformat()
    user_message = _build_user_message(goal, recent_metrics or {}, today)
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
        logger.error("claude", "generate_plan failed", {"error": str(exc)})
        raise

    data = _extract_json(message)
    cost = _estimate_cost(message.model, message.usage)
    latency_ms = round((time.monotonic() - started) * 1000)

    logger.info(
        "claude",
        "generate_plan succeeded",
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
