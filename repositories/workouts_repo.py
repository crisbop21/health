"""Derived workouts. Garmin is the source of truth; a recompute replaces the
rows for a source so it stays idempotent."""

from __future__ import annotations

from typing import Any

from core.supabase_client import get_client


def delete_source(source: str) -> None:
    get_client().table("workouts").delete().eq("source", source).execute()


def insert_many(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    resp = get_client().table("workouts").insert(rows).execute()
    return len(resp.data or [])


def get_range(start: str, end: str) -> list[dict]:
    resp = (
        get_client()
        .table("workouts")
        .select("*")
        .gte("date", start)
        .lte("date", end)
        .order("date")
        .execute()
    )
    return resp.data or []
