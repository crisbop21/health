"""Audit trail of every plan generation and recalibration."""

from __future__ import annotations

from typing import Any

from core.supabase_client import get_client


def insert(
    trigger: str,
    claude_input: Any,
    claude_output: Any,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: float | None = None,
    reason: str | None = None,
) -> dict:
    row = {
        "trigger": trigger,
        "claude_input": claude_input,
        "claude_output": claude_output,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "reason": reason,
    }
    resp = get_client().table("plan_revisions").insert(row).execute()
    return resp.data[0] if resp.data else row
