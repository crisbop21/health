"""Derived, source-resolved daily metrics. Upserted by date so a recompute is
idempotent."""

from __future__ import annotations

from typing import Any

from core.supabase_client import fetch_all, get_client, last_write_wins

_UPSERT_CHUNK = 500


def upsert_many(rows: list[dict[str, Any]]) -> int:
    written = 0
    rows = last_write_wins(rows, key=lambda r: r.get("date"))
    for i in range(0, len(rows), _UPSERT_CHUNK):
        resp = (
            get_client()
            .table("daily_metrics")
            .upsert(rows[i : i + _UPSERT_CHUNK], on_conflict="date")
            .execute()
        )
        written += len(resp.data or [])
    return written


def get_range(start: str, end: str) -> list[dict]:
    """All rows in [start, end], oldest first, paging past the per-response
    row cap so multi-year histories aren't truncated."""
    return fetch_all(
        lambda: get_client()
        .table("daily_metrics")
        .select("*")
        .gte("date", start)
        .lte("date", end)
        .order("date")
    )


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
