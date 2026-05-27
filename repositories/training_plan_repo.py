"""Generated training plan rows. Each generation writes a new version; older
versions are preserved for history."""

from __future__ import annotations

from typing import Any

from core.supabase_client import get_client


def latest_version() -> int | None:
    resp = (
        get_client()
        .table("training_plan")
        .select("version")
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    return resp.data[0]["version"] if resp.data else None


def next_version() -> int:
    current = latest_version()
    return (current + 1) if current else 1


def insert_many(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    resp = get_client().table("training_plan").insert(rows).execute()
    return len(resp.data or [])


def get_plan(version: int | None = None) -> list[dict]:
    version = version if version is not None else latest_version()
    if version is None:
        return []
    resp = (
        get_client()
        .table("training_plan")
        .select("*")
        .eq("version", version)
        .order("date")
        .execute()
    )
    return resp.data or []
