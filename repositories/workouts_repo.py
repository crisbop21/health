"""Derived workouts. Garmin is the source of truth; a recompute replaces the
rows for a source so it stays idempotent."""

from __future__ import annotations

from typing import Any

from core.supabase_client import fetch_all, get_client

_INSERT_CHUNK = 500


def delete_source(source: str) -> None:
    get_client().table("workouts").delete().eq("source", source).execute()


def insert_many(rows: list[dict[str, Any]]) -> int:
    written = 0
    for i in range(0, len(rows), _INSERT_CHUNK):
        resp = get_client().table("workouts").insert(rows[i : i + _INSERT_CHUNK]).execute()
        written += len(resp.data or [])
    return written


def get_range(start: str, end: str) -> list[dict]:
    """All rows in [start, end], oldest first, paging past the per-response
    row cap so multi-year histories aren't truncated. Dates repeat (several
    workouts a day), so id breaks ordering ties to keep pages stable."""
    return fetch_all(
        lambda: get_client()
        .table("workouts")
        .select("*")
        .gte("date", start)
        .lte("date", end)
        .order("date")
        .order("id")
    )
