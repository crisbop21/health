"""Derived, source-resolved daily metrics. Upserted by date so a recompute is
idempotent."""

from __future__ import annotations

from typing import Any

from core.supabase_client import get_client


def upsert_many(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    resp = get_client().table("daily_metrics").upsert(rows, on_conflict="date").execute()
    return len(resp.data or [])


def get_range(start: str, end: str) -> list[dict]:
    resp = (
        get_client()
        .table("daily_metrics")
        .select("*")
        .gte("date", start)
        .lte("date", end)
        .order("date")
        .execute()
    )
    return resp.data or []


def get_recent(days: int = 14) -> list[dict]:
    resp = (
        get_client()
        .table("daily_metrics")
        .select("*")
        .order("date", desc=True)
        .limit(days)
        .execute()
    )
    return list(reversed(resp.data or []))
