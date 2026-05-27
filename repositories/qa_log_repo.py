"""Question/answer log with token accounting."""

from __future__ import annotations

from typing import Any

from core.supabase_client import get_client


def insert(
    question: str,
    answer: str,
    context_sent: Any = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: float | None = None,
) -> dict:
    row = {
        "question": question,
        "answer": answer,
        "context_sent": context_sent,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
    }
    resp = get_client().table("qa_log").insert(row).execute()
    return resp.data[0] if resp.data else row


def recent(limit: int = 25) -> list[dict]:
    resp = (
        get_client()
        .table("qa_log")
        .select("*")
        .order("asked_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data or []
