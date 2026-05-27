"""Progress tests scheduled by Claude; results logged by the user."""

from __future__ import annotations

from typing import Any

from core.supabase_client import get_client


def insert_many(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    resp = get_client().table("progress_tests").insert(rows).execute()
    return len(resp.data or [])


def delete_incomplete() -> None:
    """Clear pending (not-yet-completed) tests so a reschedule replaces them
    while preserving any tests the athlete already logged results for."""
    get_client().table("progress_tests").delete().eq("completed", False).execute()


def get_all() -> list[dict]:
    resp = (
        get_client()
        .table("progress_tests")
        .select("*")
        .order("scheduled_date")
        .execute()
    )
    return resp.data or []


def upcoming(start: str, end: str) -> list[dict]:
    resp = (
        get_client()
        .table("progress_tests")
        .select("*")
        .gte("scheduled_date", start)
        .lte("scheduled_date", end)
        .order("scheduled_date")
        .execute()
    )
    return resp.data or []


def mark_complete(test_id: str, actual_result: Any, notes: str | None = None) -> dict:
    update = {"completed": True, "actual_result": actual_result}
    if notes is not None:
        update["notes"] = notes
    resp = (
        get_client()
        .table("progress_tests")
        .update(update)
        .eq("id", test_id)
        .execute()
    )
    return resp.data[0] if resp.data else update
