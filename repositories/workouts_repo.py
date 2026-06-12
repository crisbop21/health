"""Derived workouts. Each row carries a stable (source, external_id) identity
so recompute can upsert idempotently instead of delete-and-reinsert; a full
rebuild still clears a source first to drop rows deleted upstream."""

from __future__ import annotations

from typing import Any

from core.supabase_client import fetch_all, get_client, last_write_wins

_UPSERT_CHUNK = 500
_IN_CHUNK = 200  # keep `in_()` filter lists at a sane URL length


def delete_source(source: str) -> None:
    get_client().table("workouts").delete().eq("source", source).execute()


def delete_source_dates(source: str, dates: list[str]) -> None:
    """Delete a source's rows on specific dates (e.g. Whoop fallback rows on a
    day where Garmin data has now arrived)."""
    for i in range(0, len(dates), _IN_CHUNK):
        (
            get_client()
            .table("workouts")
            .delete()
            .eq("source", source)
            .in_("date", dates[i : i + _IN_CHUNK])
            .execute()
        )


def dates_with_source(source: str, dates: list[str]) -> set[str]:
    """Of `dates`, the subset that already has a workout row from `source`."""
    found: set[str] = set()
    for i in range(0, len(dates), _IN_CHUNK):
        resp = (
            get_client()
            .table("workouts")
            .select("date")
            .eq("source", source)
            .in_("date", dates[i : i + _IN_CHUNK])
            .execute()
        )
        found.update(row["date"] for row in (resp.data or []) if row.get("date"))
    return found


def upsert_many(rows: list[dict[str, Any]]) -> int:
    written = 0
    rows = last_write_wins(rows, key=lambda r: (r.get("source"), r.get("external_id")))
    for i in range(0, len(rows), _UPSERT_CHUNK):
        resp = (
            get_client()
            .table("workouts")
            .upsert(rows[i : i + _UPSERT_CHUNK], on_conflict="source,external_id")
            .execute()
        )
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
